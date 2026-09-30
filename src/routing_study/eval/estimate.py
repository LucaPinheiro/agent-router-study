"""Cost estimate before a run: measured $/case from earlier results of the same config when
available, else an a-priori upper bound from OpenRouter prices and token assumptions."""

from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any

import httpx

from routing_study.eval.rescore import load_raw
from routing_study.graph.nodes import max_tool_rounds
from routing_study.settings import Settings

# a-priori token assumptions per case (upper bound: every cascade step runs, every Jev parse
# retry fires, the executor uses its whole tool budget + wrap-up, no prompt cache)
ROUTER_PROMPT, ROUTER_COMPLETION = 900, 80  # per LLM/Jev routing call
EMBED_TOKENS = 40  # per embedded query
EXECUTOR_PROMPT, EXECUTOR_COMPLETION = 6000, 250  # per executor call


def executor_calls(settings: Settings) -> int:
    """Max executor calls per turn: one per tool round, then the wrap-up answer."""
    return max_tool_rounds(settings) + 1


async def _prices(settings: Settings) -> dict[str, tuple[float, float]]:
    base = settings.openrouter_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}"}
    out: dict[str, tuple[float, float]] = {}
    async with httpx.AsyncClient(timeout=settings.request_timeout_s) as client:
        for path in ("/models", "/embeddings/models"):
            r = await client.get(f"{base}{path}", headers=headers)
            r.raise_for_status()
            for m in r.json()["data"]:
                p = m.get("pricing") or {}
                out[m["id"]] = (float(p.get("prompt") or 0), float(p.get("completion") or 0))
    return out


def measured_cost(config: str, mode: str, results_dir: Path = Path("results")) -> float | None:
    rows = [
        r
        for r in load_raw(sorted(results_dir.glob("*.jsonl")))
        if r.get("config") == config and r.get("mode") == mode and not r.get("error")
    ]
    return mean(r["cost_usd"]["total"] for r in rows) if rows else None


def apriori_cost(
    settings: Settings, mode: str, prices: dict[str, tuple[float, float]]
) -> tuple[float, list[str]]:
    notes: list[str] = []

    def call(model: str, prompt: int, completion: int) -> float:
        if model not in prices:  # never price an unknown slug as free
            raise ValueError(f"no OpenRouter price for configured model {model!r}")
        pin, pout = prices[model]
        if pin < 0 or pout < 0:
            notes.append(f"{model}: no list price (pricing -1); counted as 0")
            return 0.0
        return pin * prompt + pout * completion

    total = 0.0
    r, s = settings.routing, settings.strategies
    if r.mode != "native":
        steps = [st.strategy for stage in (r.skill, r.tool) for st in stage.pipeline]
        if r.mode == "shadow":
            steps = [
                n for n in ("regex", "bm25", "embedding", "llm", "jev", "hybrid") if getattr(s, n)
            ] * 2
        for name in steps:
            if name == "llm" and s.llm:
                total += call(s.llm.model, ROUTER_PROMPT, ROUTER_COMPLETION)
            elif name == "jev" and s.jev:
                total += (s.jev.parse_retries + 1) * call(
                    s.jev.model, ROUTER_PROMPT, ROUTER_COMPLETION
                )
            elif name in ("embedding", "hybrid") and s.embedding:
                total += call(s.embedding.model, EMBED_TOKENS, 0)
    if mode == "e2e" and settings.executor:
        total += executor_calls(settings) * call(
            settings.executor.model, EXECUTOR_PROMPT, EXECUTOR_COMPLETION
        )
    return total, sorted(set(notes))


async def estimate(settings: Settings, n_cases: int, reps: int, mode: str) -> str:
    runs = n_cases * reps
    measured = measured_cost(settings.experiment_id, mode)
    per_case, notes = apriori_cost(settings, mode, await _prices(settings))
    lines: list[Any] = [
        f"{settings.experiment_id} [{mode}] {n_cases} cases x {reps} reps = {runs} turns"
    ]
    if measured is not None:
        lines.append(f"  measured : ${measured:.5f}/case -> ${measured * runs:.2f}")
    lines.append(f"  a priori : ${per_case:.5f}/case -> ${per_case * runs:.2f} (upper bound)")
    lines += [f"  note: {n}" for n in notes]
    return "\n".join(lines)
