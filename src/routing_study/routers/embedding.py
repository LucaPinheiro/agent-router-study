"""Dense-embedding router: cosine of the message against each option's example vectors.

- similarity `max_example`: option score = max cosine over the option's utterance vectors.
- similarity `centroid`:    option score = cosine to the mean of those vectors.
- similarity `topk_vote`:   kNN over ALL utterances: the `top_k` nearest utterances vote for
  their option with their cosine; option score = vote sum / top_k (+ 1e-3 * max cosine, which
  only orders the options without a vote).
- confidence `softmax`: softmax(scores / T)[top]; `margin`: clip((top1 - top2) / scale).
Utterances = examples + description (+ `shots`: the catalog example messages resolved to the
option, i.e. a skill's tool examples). Catalog text only.
Query = the message, or with `history_turns` > 0 the last turns + the message concatenated
(one text). Instruction-aware embedders: the query goes through `embedder.query_text` (e.g. the
Qwen3-Embedding `Instruct: …\nQuery:` prefix); option texts (documents) are embedded as-is.
Option vectors are cached on disk per (model, text). Query vectors are cached too (per model
and full query text, with the original call latency/tokens), so a grid over similarity /
temperature re-embeds nothing; such a hit reports the original latency and `cached=True`.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, ClassVar, Literal, Protocol

import diskcache
import numpy as np

from routing_study.llm import EmbeddingResult
from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput
from routing_study.routers.calibration import Calibration
from routing_study.routers.common import (
    BaseRouter,
    ResponseCache,
    abstain,
    clamp01,
    turns_text,
)

Similarity = Literal["max_example", "centroid", "topk_vote"]


class Embedder(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> EmbeddingResult: ...


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n == 0, 1.0, n)


def softmax(scores: np.ndarray, temperature: float) -> np.ndarray:
    z = (scores - scores.max()) / temperature
    e = np.exp(z)
    return e / e.sum()


class EmbeddingRouter(BaseRouter):
    name: ClassVar[str] = "embedding"
    paid: ClassVar[bool] = True

    def __init__(
        self,
        embedder: Embedder,
        *,
        vector_cache_dir: str | None = None,
        similarity: Similarity = "max_example",
        top_k: int = 5,
        confidence: Literal["margin", "softmax"] = "softmax",
        softmax_temperature: float = 0.05,
        margin_scale: float = 0.1,
        history_turns: int = 0,
        shots: bool = False,
        cache: ResponseCache | None = None,
        calibration: dict[str, Calibration] | None = None,
    ) -> None:
        super().__init__(cache=cache, calibration=calibration)
        self.embedder = embedder
        self.similarity: Similarity = similarity
        self.top_k = top_k
        self.confidence_mode = confidence
        self.softmax_temperature = softmax_temperature
        self.margin_scale = margin_scale
        self.history_turns = history_turns
        self.shots = shots
        self._vectors = (
            diskcache.Cache(vector_cache_dir, disk=diskcache.JSONDisk) if vector_cache_dir else None
        )  # JSON, never pickle
        self._mem: dict[str, Any] = {}

    @property
    def model(self) -> str | None:
        return self.embedder.model

    def cache_params(self, inp: RoutingInput, options: list[RouteOption]) -> dict[str, Any]:
        prefs = getattr(self.embedder, "provider", None)
        params = {
            "model": self.embedder.model,
            "similarity": self.similarity,
            "confidence": self.confidence_mode,
            "softmax_temperature": self.softmax_temperature,
            "margin_scale": self.margin_scale,
            "provider": prefs.model_dump(mode="json") if prefs is not None else None,
            "query_instruction": getattr(self.embedder, "query_instruction", None),
        }
        # new knobs only when set: keys of the original configuration stay as they were
        if self.similarity == "topk_vote":
            params["top_k"] = self.top_k
        if self.history_turns:
            params["history_turns"] = self.history_turns
        if self.shots:
            # shots are excluded from option dumps: key on their text explicitly
            params["shots"] = [o.shots for o in options]
        return params

    def _vkey(self, text: str) -> str:
        return hashlib.sha256(f"{self.embedder.model}\x00{text}".encode()).hexdigest()

    def _get(self, key: str) -> Any:
        if key in self._mem:
            return self._mem[key]
        if self._vectors is not None:
            raw = self._vectors.get(key)
            if raw is not None:
                self._mem[key] = raw
                return raw
        return None

    def _put(self, key: str, value: Any) -> None:
        self._mem[key] = value
        if self._vectors is not None:
            self._vectors.set(key, value)

    def _lookup(self, key: str) -> np.ndarray | None:
        raw = self._get(key)
        if raw is None:
            return None
        if not isinstance(raw, np.ndarray):
            raw = self._mem[key] = np.asarray(raw, dtype=np.float32)
        return raw

    def option_texts(self, opt: RouteOption) -> list[str]:
        texts = [*opt.examples, *(opt.shots if self.shots else []), opt.description]
        return list(dict.fromkeys(texts))

    async def text_vectors(self, texts: list[str]) -> tuple[np.ndarray, EmbeddingResult | None]:
        """Unit document vectors (no query instruction), cached; (vectors, call or None)."""
        missing = sorted({t for t in texts if self._lookup(self._vkey(t)) is None})
        res = None
        if missing:
            res = await self.embedder.embed(missing)
            for text, vec in zip(missing, _unit(res.vectors), strict=True):
                key = self._vkey(text)
                self._put(key, vec.tolist())
                self._mem[key] = vec
        return np.stack([self._lookup(self._vkey(t)) for t in texts]), res  # type: ignore[misc]

    async def option_vectors(
        self, options: list[RouteOption]
    ) -> tuple[dict[str, np.ndarray], EmbeddingResult | None]:
        """Unit vectors per option (rows = texts). Returns (vectors, index build call or None
        when every vector was cached)."""
        texts_by_opt = {o.id: self.option_texts(o) for o in options}
        flat = [t for ts in texts_by_opt.values() for t in ts]
        mat, res = await self.text_vectors(flat)
        out: dict[str, np.ndarray] = {}
        i = 0
        for oid, ts in texts_by_opt.items():
            out[oid] = mat[i : i + len(ts)]
            i += len(ts)
        return out, res

    def query_string(self, inp: RoutingInput, instruct: bool = True) -> str:
        """The text that is embedded as the query (history concatenated, instruction added
        unless `instruct=False`)."""
        past = turns_text(inp, self.history_turns)
        text = f"{past}\n{inp.message}" if past else inp.message
        query_text = getattr(self.embedder, "query_text", None)
        return query_text(text) if query_text and instruct else text

    async def embed_query(
        self, inp: RoutingInput, instruct: bool = True
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """(unit query vector, call info). A cached query vector keeps its original call
        latency/tokens and has `cached=True`."""
        text = self.query_string(inp, instruct)
        key = "q\x00" + self._vkey(text)
        hit = self._get(key)
        if isinstance(hit, dict) and "v" in hit:
            return np.asarray(hit["v"], dtype=np.float32), {**hit["info"], "cached": True}
        # asymmetric embedders (Bedrock Cohere) encode queries with their own input type
        embed_q = getattr(self.embedder, "embed_search_query", None) or self.embedder.embed
        q = await embed_q([text])
        vec = _unit(np.asarray(q.vectors[0], dtype=np.float32))
        info = {
            "cost_usd": q.cost_usd,
            "prompt_tokens": q.prompt_tokens,
            "served_model": q.served_model,
            "provider": q.provider,
            "attempts": q.attempts,
            "call_ms": q.latency_ms,
            "queue_ms": q.queue_ms,
            "retry_ms": q.retry_ms,
        }
        self._put(key, {"v": vec.tolist(), "info": info})
        return vec, {**info, "cached": False}

    def _confidence(self, scores: np.ndarray) -> float:
        order = np.sort(scores)[::-1]
        if self.confidence_mode == "margin":
            gap = order[0] - (order[1] if len(order) > 1 else 0.0)
            return clamp01(gap / self.margin_scale)
        return clamp01(float(softmax(scores, self.softmax_temperature).max()))

    def option_scores(self, vectors: dict[str, np.ndarray], qv: np.ndarray) -> np.ndarray:
        ids = list(vectors)
        if self.similarity == "centroid":
            return np.array([float(_unit(vectors[i].mean(axis=0)) @ qv) for i in ids])
        sims = {i: vectors[i] @ qv for i in ids}
        best = np.array([float(sims[i].max()) for i in ids])
        if self.similarity == "max_example":
            return best
        pooled = sorted(
            ((float(s), j) for j, i in enumerate(ids) for s in sims[i]), key=lambda t: -t[0]
        )
        votes = np.zeros(len(ids))
        for s, j in pooled[: self.top_k]:
            votes[j] += s
        return votes / self.top_k + 1e-3 * best

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        if not options or not inp.message.strip():
            return abstain(self.name)
        t0 = time.perf_counter()
        vectors, index = await self.option_vectors(options)
        t1 = time.perf_counter()
        qv, q = await self.embed_query(inp)
        t2 = time.perf_counter()
        ids = [o.id for o in options]
        scores = self.option_scores(vectors, qv)
        order = np.argsort(-scores, kind="stable")
        compute_ms = (time.perf_counter() - t2) * 1000
        index_ms = (t1 - t0) * 1000 - index.queue_ms - index.retry_ms if index is not None else 0.0
        # query embedding: its original HTTP latency when served from the vector cache
        query_ms = q["call_ms"] if q["cached"] else (t2 - t1) * 1000 - q["queue_ms"] - q["retry_ms"]
        waits = [index] if index is not None else []
        return RouteDecision(
            choice=ids[int(order[0])],
            confidence=self._confidence(scores),
            candidates=[(ids[int(i)], round(float(scores[i]), 4)) for i in order],
            strategy=self.name,
            cost_usd=q["cost_usd"],
            cached=bool(q["cached"]),
            latency_ms=max(1e-3, max(0.0, index_ms) + max(0.0, query_ms) + compute_ms),
            usage={
                "calls": 1,
                "prompt_tokens": q["prompt_tokens"],
                "served_model": q["served_model"],
                "provider": q["provider"],
                "index_cost_usd": index.cost_usd if index is not None else 0.0,
                "attempts": q["attempts"],
                "queue_ms": (0.0 if q["cached"] else q["queue_ms"])
                + sum(c.queue_ms for c in waits),
                "retry_ms": (0.0 if q["cached"] else q["retry_ms"])
                + sum(c.retry_ms for c in waits),
                "query_vector_cached": bool(q["cached"]),
            },
        )
