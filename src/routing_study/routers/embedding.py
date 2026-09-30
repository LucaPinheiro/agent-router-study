"""Dense-embedding router: cosine of the message against each option's example vectors.

- similarity `max_example`: option score = max cosine over (examples + description) vectors.
- similarity `centroid`:    option score = cosine to the mean of those vectors.
- confidence `softmax`: softmax(scores / T)[top]; `margin`: clip((top1 - top2) / scale).
Option vectors are cached on disk per (model, text); only the message is embedded per request.
Instruction-aware embedders: the message (query) goes through `embedder.query_text` (e.g. the
Qwen3-Embedding `Instruct: …\nQuery:` prefix); option texts (documents) are embedded as-is.
"""

from __future__ import annotations

import hashlib
from typing import Any, ClassVar, Literal, Protocol

import diskcache
import numpy as np

from routing_study.llm import EmbeddingResult
from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput
from routing_study.routers.common import BaseRouter, ResponseCache, abstain, clamp01


class Embedder(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> EmbeddingResult: ...


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n == 0, 1.0, n)


class EmbeddingRouter(BaseRouter):
    name: ClassVar[str] = "embedding"
    paid: ClassVar[bool] = True

    def __init__(
        self,
        embedder: Embedder,
        *,
        vector_cache_dir: str | None = None,
        similarity: Literal["max_example", "centroid"] = "max_example",
        confidence: Literal["margin", "softmax"] = "softmax",
        softmax_temperature: float = 0.05,
        margin_scale: float = 0.1,
        cache: ResponseCache | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self.embedder = embedder
        self.similarity = similarity
        self.confidence_mode = confidence
        self.softmax_temperature = softmax_temperature
        self.margin_scale = margin_scale
        self._vectors = (
            diskcache.Cache(vector_cache_dir, disk=diskcache.JSONDisk) if vector_cache_dir else None
        )  # JSON, never pickle
        self._mem: dict[str, np.ndarray] = {}

    @property
    def model(self) -> str | None:
        return self.embedder.model

    def cache_params(self, inp: RoutingInput, options: list[RouteOption]) -> dict[str, Any]:
        prefs = getattr(self.embedder, "provider", None)
        return {
            "model": self.embedder.model,
            "similarity": self.similarity,
            "confidence": self.confidence_mode,
            "softmax_temperature": self.softmax_temperature,
            "margin_scale": self.margin_scale,
            "provider": prefs.model_dump(mode="json") if prefs is not None else None,
            "query_instruction": getattr(self.embedder, "query_instruction", None),
        }

    def _vkey(self, text: str) -> str:
        return hashlib.sha256(f"{self.embedder.model}\x00{text}".encode()).hexdigest()

    def _lookup(self, key: str) -> np.ndarray | None:
        if key in self._mem:
            return self._mem[key]
        if self._vectors is not None:
            raw = self._vectors.get(key)
            if raw is not None:
                vec = self._mem[key] = np.asarray(raw, dtype=np.float32)
                return vec
        return None

    async def option_vectors(
        self, options: list[RouteOption]
    ) -> tuple[dict[str, np.ndarray], EmbeddingResult | None]:
        """Unit vectors per option (rows = texts). Returns (vectors, index build call or None
        when every vector was cached)."""
        texts_by_opt = {o.id: [*o.examples, o.description] for o in options}
        missing = sorted(
            {t for ts in texts_by_opt.values() for t in ts if self._lookup(self._vkey(t)) is None}
        )
        res = None
        if missing:
            res = await self.embedder.embed(missing)
            for text, vec in zip(missing, _unit(res.vectors), strict=True):
                key = self._vkey(text)
                self._mem[key] = vec
                if self._vectors is not None:
                    self._vectors.set(key, vec.tolist())
        out = {
            oid: np.stack([self._lookup(self._vkey(t)) for t in ts])  # type: ignore[misc]
            for oid, ts in texts_by_opt.items()
        }
        return out, res

    def _confidence(self, scores: np.ndarray) -> float:
        order = np.sort(scores)[::-1]
        if self.confidence_mode == "margin":
            gap = order[0] - (order[1] if len(order) > 1 else 0.0)
            return clamp01(gap / self.margin_scale)
        z = (scores - scores.max()) / self.softmax_temperature
        p = np.exp(z) / np.exp(z).sum()
        return clamp01(float(p.max()))

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        if not options or not inp.message.strip():
            return abstain(self.name)
        vectors, index = await self.option_vectors(options)
        query_text = getattr(self.embedder, "query_text", None)
        q = await self.embedder.embed([query_text(inp.message) if query_text else inp.message])
        calls = [q] if index is None else [index, q]
        qv = _unit(q.vectors[0])
        ids = [o.id for o in options]
        if self.similarity == "centroid":
            scores = np.array([float(_unit(vectors[i].mean(axis=0)) @ qv) for i in ids])
        else:
            scores = np.array([float((vectors[i] @ qv).max()) for i in ids])
        order = np.argsort(-scores)
        return RouteDecision(
            choice=ids[int(order[0])],
            confidence=self._confidence(scores),
            candidates=[(ids[int(i)], round(float(scores[i]), 4)) for i in order],
            strategy=self.name,
            cost_usd=q.cost_usd,
            usage={
                "calls": 1,
                "prompt_tokens": q.prompt_tokens,
                "served_model": q.served_model,
                "provider": q.provider,
                "index_cost_usd": index.cost_usd if index is not None else 0.0,
                "attempts": q.attempts,
                "queue_ms": sum(c.queue_ms for c in calls),
                "retry_ms": sum(c.retry_ms for c in calls),
            },
        )
