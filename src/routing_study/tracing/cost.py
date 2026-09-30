"""Chat-call cost capture into Langfuse generations and a local tally, for every provider.

Reads the unified usage of the response message (`llm.extract_call_usage`): OpenRouter's
`usage.cost`, Bedrock's price-table cost, Ollama's 0, with cache read/write tokens."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult
from langfuse.langchain import CallbackHandler


def _usage(response: LLMResult) -> dict[str, Any]:
    from routing_study.llm import extract_call_usage

    gens = response.generations[0] if response.generations else []
    msg = getattr(gens[0], "message", None) if gens else None
    return extract_call_usage(msg if isinstance(msg, AIMessage) else None)


def cost_details(u: dict[str, Any]) -> dict[str, float]:
    return {"total": float(u.get("cost_usd") or 0.0)}


def usage_details(u: dict[str, Any]) -> dict[str, int]:
    """Langfuse usage: `input` = uncached prompt tokens; cache read/write reported apart."""
    read, write = int(u.get("cache_read") or 0), int(u.get("cache_write") or 0)
    return {
        "input": max(0, int(u.get("prompt_tokens") or 0) - read - write),
        "output": int(u.get("completion_tokens") or 0),
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write,
    }


class CostCallbackHandler(CallbackHandler):
    """Langfuse's handler ignores provider costs; inject the unified cost as `cost_details`.

    Relies on the private `_runs` map (run_id -> open observation), verified on langfuse 4.15.6
    by `spikes/langfuse_spike.py`. Keep langfuse pinned and re-run the spike on upgrade.
    """

    def on_llm_end(
        self, response: LLMResult, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any
    ) -> Any:
        try:
            u = _usage(response)
            if u.get("cost_reported") and (gen := self._runs.get(run_id)) is not None:
                gen.update(cost_details=cost_details(u), usage_details=usage_details(u))
        except Exception:  # tracing must never break the executor
            pass
        return super().on_llm_end(response, run_id=run_id, parent_run_id=parent_run_id, **kwargs)


class CostTally(BaseCallbackHandler):
    """Per-turn sum of executor cost/tokens for the local results file (works without Langfuse)."""

    def __init__(self) -> None:
        self.cost_usd = 0.0
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0
        self.cache_write_tokens = 0
        self.served_models: list[str] = []  # distinct, in order: what actually answered
        self.providers: list[str] = []

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = _usage(response)
        out = response.llm_output or {}
        for seen, value in (
            (self.served_models, usage.get("served_model") or out.get("model_name")),
            (self.providers, usage.get("provider") or out.get("provider")),
        ):
            if value and value not in seen:
                seen.append(value)
        self.calls += 1
        self.cost_usd += float(usage.get("cost_usd") or 0.0)
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.cached_tokens += int(usage.get("cache_read") or 0)
        self.cache_write_tokens += int(usage.get("cache_write") or 0)
