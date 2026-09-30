"""Experiment runner: dataset -> Langfuse Dataset, one traced graph run per (case, repetition),
scores in Langfuse and one JSON line per turn in `results/<run_name>.jsonl` (the local file
feeds `report` and `simulate`)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import subprocess
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from itertools import zip_longest
from pathlib import Path
from typing import IO, Any, Literal
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, ToolMessage

from routing_study import prompts
from routing_study.budget import BudgetExceededError, ledger_for
from routing_study.catalog import Catalog, CatalogProvider, McpTools
from routing_study.eval.scorers import score_turn, scorer_hash, tool_index
from routing_study.graph import nodes as graph_nodes
from routing_study.graph.builder import build_graph, redis_checkpointer
from routing_study.graph.nodes import max_tool_rounds
from routing_study.graph.state import RunContext
from routing_study.llm import (
    chat_model_for,
    model_configs,
    preload_ollama,
    unload_ollama,
    validate_models,
)
from routing_study.prompts import AVAILABLE_SKILLS, HOST_RULES
from routing_study.prompts.routers import TEMPLATE_HASH
from routing_study.routers import llm as llm_router
from routing_study.routers.base import Message, RouteOption, RoutingInput
from routing_study.routers.common import REPETITION
from routing_study.routers.pipeline import build_pipeline, build_routers, shadow_set, summary
from routing_study.settings import Settings
from routing_study.tracing import langfuse as tracing
from routing_study.tracing.cost import CostCallbackHandler, CostTally

log = logging.getLogger(__name__)
Mode = Literal["e2e", "routing-only"]
DATA_DIR = Path("data")
RESULTS_DIR = Path("results")
SAMPLE_SEED = 20260929


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    customer_id: str
    turns: list[dict[str, str]]
    expected: dict[str, Any]


def stratified_sample(
    rows: list[dict[str, Any]], limit: int, seed: int = SAMPLE_SEED
) -> list[dict[str, Any]]:
    """`limit` rows keeping the category proportions (largest remainder), drawn with a
    fixed seed; the rows keep their file order."""
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    exact = {c: limit * len(g) / len(rows) for c, g in by_cat.items()}
    quota = {c: int(x) for c, x in exact.items()}
    for c in sorted(exact, key=lambda c: (quota[c] - exact[c], c))[: limit - sum(quota.values())]:
        quota[c] += 1
    rng = random.Random(seed)
    picked = {
        id(r)
        for c in sorted(by_cat)
        for r in rng.sample(sorted(by_cat[c], key=lambda r: r["id"]), quota[c])
    }
    return [r for r in rows if id(r) in picked]


def dataset_sha256(split: str, data_dir: Path = DATA_DIR) -> str:
    """sha256 of the split file; "n/a" for in-memory cases (e.g. the integration split)."""
    path = data_dir / f"dataset_{split}.jsonl"
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "n/a"


def load_cases(split: str, limit: int | None = None, data_dir: Path = DATA_DIR) -> list[Case]:
    """Cases of a split, interleaved by category; `limit` draws a stratified, seeded sample
    so `--limit N` is representative of the category mix."""
    rows = [
        json.loads(line)
        for line in (data_dir / f"dataset_{split}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be >= 1 (omit it to run every case)")
        if limit < len(rows):
            rows = stratified_sample(rows, limit)
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    mixed = [r for group in zip_longest(*by_cat.values()) for r in group if r is not None]
    return [
        Case(
            id=r["id"],
            category=r["category"],
            customer_id=r["customer_id"],
            turns=r["turns"],
            expected=r["expected"],
        )
        for r in mixed
    ]


# ---------------------------------------------------------------- run metadata


@contextmanager
def results_writer(out: Path, *, overwrite: bool) -> Iterator[IO[str]]:
    """Rows go to `<out>.partial` (created with "x": two runs never share it) and the file is
    renamed to `out` only when the run finishes, so a crash never leaves a file that looks
    complete (review M3). A leftover .partial blocks a new run unless `overwrite`."""
    partial = out.with_name(out.name + ".partial")
    if overwrite:
        partial.unlink(missing_ok=True)
    elif partial.exists():
        raise FileExistsError(f"{partial} exists (crashed or running): pass --overwrite")
    with partial.open("x", encoding="utf-8") as fh:
        yield fh
    if out.exists() and not overwrite:
        raise FileExistsError(f"{out} appeared during the run; rows kept in {partial}")
    os.replace(partial, out)


def git_sha(cwd: Path | None = None) -> str:
    """Short HEAD sha; a dirty tree adds `-dirty.<hash of the diff + untracked files>`."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10, cwd=cwd
        ).stdout

    try:
        sha = git("rev-parse", "--short", "HEAD").strip()
        if not sha:
            return "uncommitted"
        if not git("status", "--porcelain").strip():
            return sha
        h = hashlib.sha256(git("diff", "HEAD", "--binary").encode())
        for name in sorted(git("ls-files", "--others", "--exclude-standard").splitlines()):
            h.update(b"\0" + name.encode() + b"\0")
            try:
                h.update(((cwd or Path()) / name).read_bytes())
            except OSError:
                pass
        return f"{sha}-dirty.{h.hexdigest()[:8]}"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def config_hash(settings: Settings) -> str:
    """Routing/strategies/executor config plus the content of the files it points to
    (regex rules), so editing the rules changes the hash."""
    h = hashlib.sha256(
        settings.model_dump_json(include={"routing", "strategies", "executor"}).encode()
    )
    regex = settings.strategies.regex
    if regex is not None:
        rules = Path(regex.rules_path)
        h.update(b"\0regex_rules\0" + (rules.read_bytes() if rules.exists() else b"<missing>"))
    return h.hexdigest()[:12]


def run_prompt_hash() -> str:
    """Hash of every prompt template the run uses, rendered over fixed placeholder data:
    executor system prompt (routed + native), load_skill tool, host escalation text and the
    LLM/Jev routing prompt (catalog content is covered by catalog_hash)."""
    from types import SimpleNamespace

    skill = SimpleNamespace(id="skill", description="description", markdown="playbook")
    catalog: Any = SimpleNamespace(instructions="instructions", skills={"skill": skill})
    customer = {"customer_id": "C000", "name": "Name", "orders": [{"order_id": "O0000"}]}
    parts: list[Any] = [
        prompts.system_blocks(catalog, native=native, skill=sk, customer=customer)
        for native, sk in ((False, "skill"), (True, None))
    ]
    parts += [graph_nodes.load_skill_tool(catalog), graph_nodes.ESCALATION_TEXT]
    option = RouteOption(id="option", description="description", examples=["example"])
    for level in ("skill", "tool"):
        inp = RoutingInput(
            message="message",
            level=level,
            loaded_skill="skill",
            history=[Message(role="user", content="history")],
        )
        for json_reply in (False, True):
            msgs = llm_router.build_messages(
                inp, [option], history_turns=1, allow_abstain=True, json_reply=json_reply
            )
            parts += [m.content for m in msgs]
    parts.append(TEMPLATE_HASH)  # every router prompt variant (the config picks one)
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def models_used(settings: Settings, roles: set[str] | None = None) -> dict[str, str]:
    """role -> model of the models a run calls (`roles`: strategies / "executor")."""
    out = {"executor": settings.executor.model if settings.executor else ""}
    for name, cfg in model_configs(settings, roles):
        if name != "executor" and settings.routing.mode != "native":
            out[name] = cfg.model
    return out


class ExecutorTimer(BaseCallbackHandler):
    """Executor latency of a turn: summed duration of the completed chat-model calls only
    (failed attempts and retry backoff excluded; routers do not use these callbacks)."""

    def __init__(self) -> None:
        self.ms = 0.0
        self.calls = 0
        self._start: dict[UUID, float] = {}

    def on_chat_model_start(
        self, serialized: dict[str, Any], messages: Any, *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._start[run_id] = time.perf_counter()

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        t0 = self._start.pop(run_id, None)
        if t0 is not None:
            self.ms += (time.perf_counter() - t0) * 1000
            self.calls += 1

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._start.pop(run_id, None)


# ---------------------------------------------------------------- turn record


def turn_record(
    state: dict[str, Any], catalog: Catalog, *, native: bool, mode: Mode
) -> dict[str, Any]:
    msgs = state.get("messages", [])[len(state["case"]["turns"]) :]
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
                "error" if tm is None or tm.status == "error" else "completed"
            )
            calls.append(
                {
                    "name": tc["name"],
                    "args": tc.get("args") or {},
                    "skill": catalog.skill_of(tc["name"]) if catalog.has_tool(tc["name"]) else None,
                    "status": status,
                    "structured": structured,
                }
            )
    return {
        "native": native,
        "mode": mode,
        "skill": summary(state.get("skill_decision")),
        "tool": summary(state.get("tool_decision")),
        "loaded_skill": state.get("loaded_skill"),
        "exposed_tools": state.get("exposed_tools") or [],
        "calls": calls,
        "outcome": state.get("outcome"),
        "final_answer": final_answer,
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
    overwrite: bool = False
    # per invocation: re-running the same --run-name never resumes an old checkpoint thread
    invocation: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    @property
    def config_name(self) -> str:
        return self.settings.experiment_id

    @property
    def native(self) -> bool:
        return self.settings.routing.mode == "native"

    def thread_id(self, case_id: str, rep: int) -> str:
        return f"{self.run_name}:{self.invocation}:{case_id}:{rep}"

    async def run(self, cases: list[Case]) -> Path:
        out = self._results_path()
        if out.exists() and not self.overwrite:
            raise FileExistsError(f"{out} exists: pick another --run-name or pass --overwrite")
        if self.native and self.mode == "routing-only":
            raise ValueError("routing-only needs a routed config (E1–E9); E0 has no router")
        if "native_agent" in (
            self.settings.routing.skill.on_abstain,
            self.settings.routing.tool.on_abstain,
        ):
            raise NotImplementedError("on_abstain=native_agent is not implemented (use escalate)")
        if not self.settings.redis_url:
            raise ValueError("REDIS_URL is required (catalog cache + checkpointer)")
        import redis.asyncio as aioredis

        supported = await validate_models(self.settings, names=self.model_roles())
        await self.check_budget(len(cases) * self.reps)
        await preload_ollama(self.settings, self.model_roles())
        redis = aioredis.from_url(self.settings.redis_url)
        self.catalog = CatalogProvider(self.settings, redis)
        catalog, _ = await self.catalog.get()
        self.schemas, self.read_only = tool_index(catalog.tools)
        self.skill_pipeline = self.tool_pipeline = None
        if not self.native:
            wanted = self.model_roles() - {"executor"}
            routers = build_routers(self.settings, wanted, supported_parameters=supported)
            self.skill_pipeline = build_pipeline(self.settings, "skill", routers)
            self.tool_pipeline = build_pipeline(self.settings, "tool", routers)
        self.chat = None
        if self.mode == "e2e":
            ex = self.settings.executor
            if ex is None:
                raise ValueError("e2e mode needs `executor` in the config")
            self.chat = chat_model_for(
                self.settings, ex, supported_parameters=supported.get(ex.model)
            )
        self.meta = {
            "git_sha": git_sha(),
            "config_hash": config_hash(self.settings),
            "catalog_hash": catalog.hash,
            "prompt_hash": run_prompt_hash(),
            "models": json.dumps(models_used(self.settings, self.model_roles())),
            "run_name": self.run_name,
            "config": self.config_name,
            "dataset_sha256": dataset_sha256(self.split),
            "scorer_hash": scorer_hash(),
        }
        uploaded = self.upload_dataset and self._upload(cases)
        self.prompt_versions = tracing.register_prompts(
            {"host_rules": HOST_RULES, "available_skills": AVAILABLE_SKILLS}
        )

        sem = asyncio.Semaphore(self.concurrency)
        try:
            async with redis_checkpointer(self.settings.redis_url) as saver:
                graph = build_graph(saver, routing_only=self.mode == "routing-only")
                with results_writer(out, overwrite=self.overwrite) as fh:

                    async def one(case: Case, rep: int) -> None:
                        async with sem:
                            rec = await self.run_case(
                                graph, case, rep, case.id if uploaded else None
                            )
                        fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                        fh.flush()

                    try:  # a spend cap cancels every in-flight case
                        async with asyncio.TaskGroup() as tg:
                            for rep in range(1, self.reps + 1):
                                for c in cases:
                                    tg.create_task(one(c, rep))
                    except BaseExceptionGroup as group:
                        budget = group.subgroup(BudgetExceededError)
                        if budget is not None:
                            raise budget.exceptions[0] from None
                        raise
        finally:
            await redis.aclose()
            tracing.flush()
            if any(
                c.provider == "ollama" for _, c in model_configs(self.settings, self.model_roles())
            ):
                await unload_ollama(self.settings)  # one local model resident at a time
        return out

    def model_roles(self) -> set[str]:
        """Strategies (+ "executor" in e2e) whose models this run calls."""
        r = self.settings.routing
        roles = {"executor"} if self.mode == "e2e" else set()
        if not self.native:
            roles |= {s.strategy for s in [*r.skill.pipeline, *r.tool.pipeline]}
            if r.mode == "shadow":
                roles |= set(shadow_set(self.settings))
        return roles

    async def check_budget(self, turns: int) -> None:
        """Refuse to start when ledger spend + this run's a-priori upper bound would pass an
        account cap (per provider: AWS for Bedrock, OpenRouter)."""
        from routing_study.eval.estimate import apriori_costs, list_prices

        by, _ = apriori_costs(self.settings, self.mode, await list_prices(self.settings))
        ledger = ledger_for(self.settings)
        for provider, per_turn in by.items():
            ledger.check(provider, per_turn * turns, what=f"projected run ({turns} turns)")

    def base_record(self, case: Case, rep: int) -> dict[str, Any]:
        """Row identity + provenance (review M2): code version, config/catalog/prompt hashes,
        dataset and scorer hashes, so rows of different versions never mix silently."""
        keys = (
            "git_sha",
            "config_hash",
            "catalog_hash",
            "prompt_hash",
            "dataset_sha256",
            "scorer_hash",
        )
        return {
            "run_name": self.run_name,
            "config": self.config_name,
            "split": self.split,
            "case_id": case.id,
            "category": case.category,
            "rep": rep,
            "expected": case.expected,
            **{k: self.meta.get(k) for k in keys},
        }

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
            lf.create_dataset_item(
                dataset_name=name,
                id=c.id,
                input={"customer_id": c.customer_id, "turns": c.turns},
                expected_output=c.expected,
                metadata={"category": c.category, "split": self.split},
            )
        return True

    async def run_case(
        self, graph: Any, case: Case, rep: int, item_id: str | None
    ) -> dict[str, Any]:
        tally = CostTally()
        timer = ExecutorTimer()
        callbacks: list[Any] = [tally, timer]
        if tracing.enabled():
            callbacks.append(CostCallbackHandler())
        base = self.base_record(case, rep)
        tags = [self.config_name, self.split, f"rep{rep}", self.mode, self.run_name]
        t0 = time.perf_counter()
        with tracing.turn(
            session_id=case.id,
            tags=tags,
            metadata=self.meta,
            input={"turns": case.turns, "customer_id": case.customer_id},
        ) as (root, trace_id):
            if item_id and trace_id:
                try:
                    await tracing.client().async_api.dataset_run_items.create(
                        run_name=self.run_name,
                        dataset_item_id=item_id,
                        trace_id=trace_id,
                        observation_id=root.id,
                        metadata={"config": self.config_name, "rep": rep},
                    )
                except Exception:
                    log.warning("dataset_run_items.create failed", exc_info=True)
            try:
                async with McpTools(self.settings, case.customer_id) as mcp:
                    ctx = RunContext(
                        settings=self.settings,
                        catalog=self.catalog,
                        tools=mcp,
                        chat=self.chat,
                        skill_pipeline=self.skill_pipeline,
                        tool_pipeline=self.tool_pipeline,
                        callbacks=callbacks,
                        prompt_versions=self.prompt_versions,
                    )
                    REPETITION.set(rep)  # task-local: response-cache key per repetition
                    state = await graph.ainvoke(
                        {
                            "case": {
                                "case_id": case.id,
                                "customer_id": case.customer_id,
                                "split": self.split,
                                "repetition": rep,
                                "turns": case.turns,
                            }
                        },
                        config={
                            "configurable": {"thread_id": self.thread_id(case.id, rep)},
                            # backstop: 3 routing nodes + (agent, tools) per round + wrap-up
                            "recursion_limit": 2 * max_tool_rounds(self.settings) + 6,
                        },
                        context=ctx,
                    )
                catalog, _ = await self.catalog.get()
                rec = turn_record(state, catalog, native=self.native, mode=self.mode)
                scores = score_turn(
                    rec, case.expected, self.schemas, turns=case.turns, read_only=self.read_only
                )
                # a failed consulted router is an error row, not a scored abstention
                error = next(
                    (
                        st["routing_error"]
                        for st in (rec["skill"], rec["tool"])
                        if st and st.get("routing_error")
                    ),
                    None,
                )
            except BudgetExceededError:
                raise  # the spend cap aborts the whole run
            except Exception as exc:  # one broken case never kills the batch
                log.exception("case %s rep %s failed", case.id, rep)
                rec, scores, error = {}, {}, f"{type(exc).__name__}: {exc}"[:500]
            latency = (time.perf_counter() - t0) * 1000
            root.update(
                output={
                    "final_answer": rec.get("final_answer"),
                    "outcome": rec.get("outcome"),
                    "error": error,
                },
                level="ERROR" if error else "DEFAULT",
            )

        def stages(key: str) -> float:
            return sum((rec.get(k) or {}).get(key, 0.0) for k in ("skill", "tool"))

        routing_cost = stages("cost_usd")  # consulted steps: what production would pay
        routing_billed = stages("billed_usd")  # what this run paid (router cache hits free)
        rec = {
            **base,
            "trace_id": trace_id,
            "mode": self.mode,
            **rec,
            "error": error,
            "scores": scores,
            "cost_usd": {
                "routing": routing_cost,
                "routing_shadow": stages("shadow_cost_usd"),
                "agent": tally.cost_usd,
                "total": routing_cost + tally.cost_usd,  # study cost (cache-independent)
                "routing_billed": routing_billed,
                "billed_total": routing_billed + tally.cost_usd,  # paid
            },
            "executor": {"served_models": tally.served_models, "providers": tally.providers},
            "tokens": {
                "prompt": tally.prompt_tokens,
                "completion": tally.completion_tokens,
                "cached": tally.cached_tokens,
                "cache_write": tally.cache_write_tokens,
                "agent_calls": tally.calls,
            },
            "latency_ms": {
                "turn": latency,
                "routing": stages("latency_ms"),
                "executor": timer.ms if self.mode == "e2e" else None,
            },
        }
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
                lf.create_score(trace_id=trace_id, name=name, value=value, data_type="CATEGORICAL")
            else:
                lf.create_score(
                    trace_id=trace_id, name=name, value=float(value), data_type="NUMERIC"
                )


def default_run_name(config_name: str, split: str, mode: str) -> str:
    return f"{config_name}-{split}-{mode}-{datetime.now():%Y%m%d-%H%M%S}"
