"""Experiment runner: dataset -> Langfuse Dataset, one traced graph run per (case, repetition),
scores in Langfuse and one JSON line per turn in `results/<run_name>.jsonl` (the local file
feeds `report` and `simulate`)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from itertools import zip_longest
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage, ToolMessage

from routing_study.catalog import Catalog, CatalogProvider, McpTools
from routing_study.eval.scorers import score_turn
from routing_study.graph.builder import build_graph, redis_checkpointer
from routing_study.graph.nodes import max_tool_rounds
from routing_study.graph.state import RunContext
from routing_study.llm import make_chat_model, validate_models
from routing_study.prompts import AVAILABLE_SKILLS, HOST_RULES, PROMPT_HASH
from routing_study.routers.pipeline import build_pipeline, build_routers, summary
from routing_study.settings import Settings
from routing_study.tracing import langfuse as tracing
from routing_study.tracing.cost import CostCallbackHandler, CostTally

log = logging.getLogger(__name__)
Mode = Literal["e2e", "routing-only"]
DATA_DIR = Path("data")
RESULTS_DIR = Path("results")


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    customer_id: str
    turns: list[dict[str, str]]
    expected: dict[str, Any]


def load_cases(split: str, limit: int | None = None, data_dir: Path = DATA_DIR) -> list[Case]:
    """Cases of a split, interleaved by category so `--limit N` is a representative slice."""
    rows = [json.loads(line) for line in (data_dir / f"dataset_{split}.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    mixed = [r for group in zip_longest(*by_cat.values()) for r in group if r is not None]
    cases = [Case(id=r["id"], category=r["category"], customer_id=r["customer_id"],
                  turns=r["turns"], expected=r["expected"]) for r in mixed]
    return cases[:limit] if limit else cases


# ---------------------------------------------------------------- run metadata


def git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=5)
        return out.stdout.strip() or "uncommitted"
    except OSError:
        return "unknown"


def config_hash(settings: Settings) -> str:
    raw = settings.model_dump_json(include={"routing", "strategies", "executor"})
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def models_used(settings: Settings) -> dict[str, str]:
    s = settings.strategies
    out = {"executor": settings.executor.model if settings.executor else ""}
    for name in ("llm", "jev", "embedding"):
        cfg = getattr(s, name)
        if cfg is not None and settings.routing.mode != "native":
            out[name] = cfg.model
    return out


# ---------------------------------------------------------------- turn record


def turn_record(state: dict[str, Any], catalog: Catalog, *, native: bool,
                mode: Mode) -> dict[str, Any]:
    msgs = state.get("messages", [])[len(state["case"]["turns"]):]
    results = {m.tool_call_id: m for m in msgs if isinstance(m, ToolMessage)}
    calls: list[dict[str, Any]] = []
    final_answer = None
    for m in msgs:
        if not isinstance(m, AIMessage):
            continue
        if not m.tool_calls and m.name != "host":
            final_answer = m.text
        for tc in m.tool_calls:
            tm = results.get(tc["id"])
            art = (tm.artifact if tm is not None else None) or {}
            structured = art.get("structured")
            status = (structured or {}).get("status") or (
                "error" if tm is None or tm.status == "error" else "completed")
            calls.append({"name": tc["name"], "args": tc.get("args") or {},
                          "skill": catalog.skill_of(tc["name"])
                          if catalog.has_tool(tc["name"]) else None,
                          "status": status, "structured": structured})
    return {
        "native": native, "mode": mode,
        "skill": summary(state.get("skill_decision")),
        "tool": summary(state.get("tool_decision")),
        "loaded_skill": state.get("loaded_skill"),
        "exposed_tools": state.get("exposed_tools") or [],
        "calls": calls, "outcome": state.get("outcome"), "final_answer": final_answer,
        "customer": state.get("customer"),
    }


# ---------------------------------------------------------------- runner


@dataclass
class Runner:
    settings: Settings
    split: str
    mode: Mode
    run_name: str
    reps: int = 1
    concurrency: int = 4
    upload_dataset: bool = True

    @property
    def config_name(self) -> str:
        return self.settings.experiment_id

    @property
    def native(self) -> bool:
        return self.settings.routing.mode == "native"

    async def run(self, cases: list[Case]) -> Path:
        if self.native and self.mode == "routing-only":
            raise ValueError("routing-only needs a routed config (E1–E9); E0 has no router")
        if "native_agent" in (self.settings.routing.skill.on_abstain,
                              self.settings.routing.tool.on_abstain):
            raise NotImplementedError("on_abstain=native_agent is not implemented (use escalate)")
        if not self.settings.redis_url:
            raise ValueError("REDIS_URL is required (catalog cache + checkpointer)")
        import redis.asyncio as aioredis

        supported = await validate_models(self.settings)
        redis = aioredis.from_url(self.settings.redis_url)
        self.catalog = CatalogProvider(self.settings, redis)
        catalog, _ = await self.catalog.get()
        self.schemas = {t["name"]: t.get("inputSchema") or {} for t in catalog.tools}
        self.skill_pipeline = self.tool_pipeline = None
        if not self.native:
            r = self.settings.routing
            wanted = None if r.mode == "shadow" else {
                s.strategy for s in [*r.skill.pipeline, *r.tool.pipeline]}
            routers = build_routers(self.settings, wanted, supported_parameters=supported)
            self.skill_pipeline = build_pipeline(self.settings, "skill", routers)
            self.tool_pipeline = build_pipeline(self.settings, "tool", routers)
        self.chat = None
        if self.mode == "e2e":
            ex = self.settings.executor
            if ex is None:
                raise ValueError("e2e mode needs `executor` in the config")
            self.chat = make_chat_model(self.settings, ex.model, temperature=ex.temperature,
                                        seed=ex.seed, provider=ex.provider, max_tokens=1024,
                                        supported_parameters=supported.get(ex.model))
        self.meta = {"git_sha": git_sha(), "config_hash": config_hash(self.settings),
                     "catalog_hash": catalog.hash, "prompt_hash": PROMPT_HASH,
                     "models": json.dumps(models_used(self.settings)),
                     "run_name": self.run_name, "config": self.config_name}
        uploaded = self.upload_dataset and self._upload(cases)
        self.prompt_versions = tracing.register_prompts(
            {"host_rules": HOST_RULES, "available_skills": AVAILABLE_SKILLS})

        out = self._results_path()
        sem = asyncio.Semaphore(self.concurrency)
        try:
            async with redis_checkpointer(self.settings.redis_url) as saver:
                graph = build_graph(saver, routing_only=self.mode == "routing-only")
                with out.open("a", encoding="utf-8") as fh:
                    async def one(case: Case, rep: int) -> None:
                        async with sem:
                            rec = await self.run_case(graph, case, rep,
                                                      case.id if uploaded else None)
                        fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                        fh.flush()

                    await asyncio.gather(*(one(c, rep) for rep in range(1, self.reps + 1)
                                           for c in cases))
        finally:
            await redis.aclose()
            tracing.flush()
        return out

    def _results_path(self) -> Path:
        RESULTS_DIR.mkdir(exist_ok=True)
        return RESULTS_DIR / f"{self.run_name}.jsonl"

    def _upload(self, cases: list[Case]) -> bool:
        """Langfuse dataset items keyed by case id; False when tracing is off."""
        if not tracing.enabled():
            return False
        lf = tracing.client()
        name = f"routing-study-{self.split}"
        lf.create_dataset(name=name, description=f"routing study, split {self.split}")
        for c in cases:
            lf.create_dataset_item(dataset_name=name, id=c.id,
                                   input={"customer_id": c.customer_id, "turns": c.turns},
                                   expected_output=c.expected,
                                   metadata={"category": c.category, "split": self.split})
        return True

    async def run_case(self, graph: Any, case: Case, rep: int,
                       item_id: str | None) -> dict[str, Any]:
        tally = CostTally()
        callbacks: list[Any] = [tally]
        if tracing.enabled():
            callbacks.append(CostCallbackHandler())
        base = {"run_name": self.run_name, "config": self.config_name, "split": self.split,
                "case_id": case.id, "category": case.category, "rep": rep,
                "expected": case.expected, **{k: self.meta[k] for k in
                                              ("config_hash", "catalog_hash", "prompt_hash")}}
        tags = [self.config_name, self.split, f"rep{rep}", self.mode, self.run_name]
        t0 = time.perf_counter()
        with tracing.turn(session_id=case.id, tags=tags, metadata=self.meta,
                          input={"turns": case.turns, "customer_id": case.customer_id}
                          ) as (root, trace_id):
            if item_id and trace_id:
                try:
                    await tracing.client().async_api.dataset_run_items.create(
                        run_name=self.run_name, dataset_item_id=item_id, trace_id=trace_id,
                        observation_id=root.id, metadata={"config": self.config_name, "rep": rep})
                except Exception:
                    log.warning("dataset_run_items.create failed", exc_info=True)
            try:
                async with McpTools(self.settings, case.customer_id) as mcp:
                    ctx = RunContext(settings=self.settings, catalog=self.catalog, tools=mcp,
                                     chat=self.chat, skill_pipeline=self.skill_pipeline,
                                     tool_pipeline=self.tool_pipeline, callbacks=callbacks,
                                     prompt_versions=self.prompt_versions)
                    state = await graph.ainvoke(
                        {"case": {"case_id": case.id, "customer_id": case.customer_id,
                                  "split": self.split, "repetition": rep, "turns": case.turns}},
                        config={"configurable": {
                            "thread_id": f"{self.run_name}:{case.id}:{rep}"},
                            # backstop: 3 routing nodes + (agent, tools) per round + wrap-up
                            "recursion_limit": 2 * max_tool_rounds(self.settings) + 6},
                        context=ctx)
                catalog, _ = await self.catalog.get()
                rec = turn_record(state, catalog, native=self.native, mode=self.mode)
                scores = score_turn(rec, case.expected, self.schemas)
                error = None
            except Exception as exc:  # one broken case never kills the batch
                log.exception("case %s rep %s failed", case.id, rep)
                rec, scores, error = {}, {}, f"{type(exc).__name__}: {exc}"[:500]
            latency = (time.perf_counter() - t0) * 1000
            root.update(output={"final_answer": rec.get("final_answer"),
                                "outcome": rec.get("outcome"), "error": error},
                        level="ERROR" if error else "DEFAULT")
        def stages(key: str) -> float:
            return sum((rec.get(k) or {}).get(key, 0.0) for k in ("skill", "tool"))

        routing_cost = stages("cost_usd")  # consulted steps: what production would pay
        rec = {**base, "trace_id": trace_id, "mode": self.mode, **rec, "error": error,
               "scores": scores,
               "cost_usd": {"routing": routing_cost, "routing_shadow": stages("shadow_cost_usd"),
                            "agent": tally.cost_usd, "total": routing_cost + tally.cost_usd},
               "tokens": {"prompt": tally.prompt_tokens, "completion": tally.completion_tokens,
                          "cached": tally.cached_tokens, "agent_calls": tally.calls},
               "latency_ms": {"turn": latency, "routing": stages("latency_ms")}}
        if trace_id:
            self._score(trace_id, scores)
        return rec

    @staticmethod
    def _score(trace_id: str, scores: dict[str, Any]) -> None:
        lf = tracing.client()
        for name, value in scores.items():
            if value is None:
                continue
            if isinstance(value, str):
                lf.create_score(trace_id=trace_id, name=name, value=value,
                                data_type="CATEGORICAL")
            else:
                lf.create_score(trace_id=trace_id, name=name, value=float(value),
                                data_type="NUMERIC")


def default_run_name(config_name: str, split: str, mode: str) -> str:
    return f"{config_name}-{split}-{mode}-{datetime.now():%Y%m%d-%H%M%S}"
