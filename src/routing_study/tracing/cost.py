"""Chat-call cost capture: OpenRouter's `usage.cost` into Langfuse generations and a local tally."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langfuse.langchain import CallbackHandler


def _usage(response: LLMResult) -> dict[str, Any]:
    return (response.llm_output or {}).get("token_usage") or {}


class CostCallbackHandler(CallbackHandler):
    """Langfuse's handler ignores OpenRouter's `usage.cost`; inject it as `cost_details`.

    Relies on the private `_runs` map (run_id -> open observation), verified on langfuse 4.15.6
    by `spikes/langfuse_spike.py`. Keep langfuse pinned and re-run the spike on upgrade.
    """

    def on_llm_end(self, response: LLMResult, *, run_id: UUID,
                   parent_run_id: UUID | None = None, **kwargs: Any) -> Any:
        try:
            cost = _usage(response).get("cost")
            if cost is not None and (gen := self._runs.get(run_id)) is not None:
                gen.update(cost_details={"total": float(cost)})
        except Exception:  # tracing must never break the executor
            pass
        return super().on_llm_end(response, run_id=run_id, parent_run_id=parent_run_id,
                                  **kwargs)


class CostTally(BaseCallbackHandler):
    """Per-turn sum of executor cost/tokens for the local results file (works without Langfuse)."""

    def __init__(self) -> None:
        self.cost_usd = 0.0
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = _usage(response)
        self.calls += 1
        self.cost_usd += float(usage.get("cost") or 0.0)
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.cached_tokens += int((usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                                  or 0)
