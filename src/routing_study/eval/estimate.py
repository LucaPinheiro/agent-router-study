"""Cost estimate before a run: measured $/case from earlier results of the same config when
available, else an a-priori upper bound from list prices and token assumptions. List prices:
OpenRouter `/models` for OpenRouter slugs, the local price table (`budget.prices_path`) for
Bedrock, 0 for Ollama. The per-provider upper bound also feeds the budget guard of `run`."""

from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any

import httpx

from routing_study.budget import prices_for
from routing_study.eval.rescore import load_raw
from routing_study.graph.nodes import max_tool_rounds
from routing_study.settings import Settings, is_llm_strategy

# a-priori token assumptions per case (upper bound: every cascade step runs, every Jev parse
# retry fires, the executor uses its whole tool budget + wrap-up, no prompt cache)
ROUTER_PROMPT, ROUTER_COMPLETION = 900, 80  # per LLM/Jev routing call
EMBED_TOKENS = 40  # per embedded query
EXECUTOR_PROMPT, EXECUTOR_COMPLETION = 6000, 250  # per executor call


def executor_calls(settings: Settings) -> int:
    """Max executor calls per turn: one per tool round, then the wrap-up answer."""
    return max_tool_rounds(settings) + 1


def _uses_openrouter(settings: Settings) -> bool:
    from routing_study.llm import model_configs

    return any(cfg.provider == "openrouter" for _, cfg in model_configs(settings))


async def list_prices(settings: Settings) -> dict[str, tuple[float, float]]:
    """model -> (USD per prompt token, USD per completion token), every provider."""
    from routing_study.llm import model_configs

    out = await _prices(settings) if _uses_openrouter(settings) else {}
    table = prices_for(settings)
    for _, cfg in model_configs(settings):
        if cfg.provider == "ollama":
            out[cfg.model] = (0.0, 0.0)
        elif cfg.provider == "bedrock" and (price := table.get(("bedrock", cfg.model))):
            out[cfg.model] = (price.input / 1e6, price.output / 1e6)
    return out


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


def apriori_costs(
    settings: Settings, mode: str, prices: dict[str, tuple[float, float]]
) -> tuple[dict[str, float], list[str]]:
    """Upper-bound USD per case, by provider (openrouter / bedrock / ollama)."""
    notes: list[str] = []
    by: dict[str, float] = {}

    def call(cfg: Any, prompt: int, completion: int, times: int = 1) -> None:
        model = cfg.model
        if model not in prices:  # never price an unknown slug as free
            raise ValueError(f"no {cfg.provider} price for configured model {model!r}")
        pin, pout = prices[model]
        if pin < 0 or pout < 0:
            notes.append(f"{model}: no list price (pricing -1); counted as 0")
            pin = pout = 0.0
        by[cfg.provider] = by.get(cfg.provider, 0.0) + times * (pin * prompt + pout * completion)

    r, s = settings.routing, settings.strategies
    if r.mode != "native":
        steps = [st.strategy for stage in (r.skill, r.tool) for st in stage.pipeline]
        if r.mode == "shadow":
            from routing_study.routers.pipeline import shadow_set

            steps = list(dict.fromkeys([*steps, *shadow_set(settings)])) * 2
        for name in steps:
            if is_llm_strategy(name) and s.get(name):
                call(s.get(name), ROUTER_PROMPT, ROUTER_COMPLETION)
            elif name == "jev" and s.jev:
                call(s.jev, ROUTER_PROMPT, ROUTER_COMPLETION, s.jev.parse_retries + 1)
            elif name in ("embedding", "hybrid") and s.embedding:
                call(s.embedding, EMBED_TOKENS, 0)
    if mode == "e2e" and settings.executor:
        call(settings.executor, EXECUTOR_PROMPT, EXECUTOR_COMPLETION, executor_calls(settings))
    return by, sorted(set(notes))


def apriori_cost(
    settings: Settings, mode: str, prices: dict[str, tuple[float, float]]
) -> tuple[float, list[str]]:
    by, notes = apriori_costs(settings, mode, prices)
    return sum(by.values()), notes


async def estimate(settings: Settings, n_cases: int, reps: int, mode: str) -> str:
    runs = n_cases * reps
    measured = measured_cost(settings.experiment_id, mode)
    by, notes = apriori_costs(settings, mode, await list_prices(settings))
    per_case = sum(by.values())
    lines: list[Any] = [
        f"{settings.experiment_id} [{mode}] {n_cases} cases x {reps} reps = {runs} turns"
    ]
    if measured is not None:
        lines.append(f"  measured : ${measured:.5f}/case -> ${measured * runs:.2f}")
    lines.append(f"  a priori : ${per_case:.5f}/case -> ${per_case * runs:.2f} (upper bound)")
    lines += [f"    {prov:<10} ${v * runs:.2f}" for prov, v in sorted(by.items())]
    lines += [f"  note: {n}" for n in notes]
    return "\n".join(lines)
