"""Shared test helpers for router tests."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import numpy as np

from routing_study.llm import EmbeddingResult
from routing_study.routers.base import RoutingInput

BASE_URL = "https://openrouter.test/api/v1"


def skill_input(message: str, **kw: Any) -> RoutingInput:
    return RoutingInput(message=message, level="skill", **kw)


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder; counts calls/texts."""

    model = "fake/embed"

    def __init__(self, dim: int = 256, cost_per_text: float = 1e-6) -> None:
        self.dim = dim
        self.cost_per_text = cost_per_text
        self.calls: list[list[str]] = []

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in re.findall(r"\w+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        return v

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        self.calls.append(list(texts))
        return EmbeddingResult(
            vectors=np.stack([self._vec(t) for t in texts]),
            cost_usd=self.cost_per_text * len(texts),
            served_model="Fake/Embed",
            provider="FakeProvider",
            prompt_tokens=sum(len(t.split()) for t in texts),
            latency_ms=1.0,
        )


def chat_completion(content: str, *, model: str = "anthropic/claude-haiku-4.5",
                    provider: str = "Anthropic", cost: float = 0.0003) -> dict[str, Any]:
    return {
        "id": "gen-test",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "provider": provider,
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110,
                  "cost": cost},
    }
