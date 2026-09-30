"""BM25 router (local): one document per option = description + examples + keywords.

Confidence = normalized margin (top1 - top2) / top1; abstains when nothing scores.
"""

from __future__ import annotations

from typing import ClassVar

from rank_bm25 import BM25Okapi

from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput
from routing_study.routers.common import BaseRouter, abstain, clamp01, option_document, tokenize


class BM25Router(BaseRouter):
    name: ClassVar[str] = "bm25"

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        super().__init__(cache=None)
        self.k1 = k1
        self.b = b
        self._index: dict[tuple[str, ...], BM25Okapi] = {}

    def _bm25(self, options: list[RouteOption]) -> BM25Okapi:
        key = tuple(o.model_dump_json() for o in options)
        idx = self._index.get(key)
        if idx is None:
            corpus = [tokenize(option_document(o)) or ["_"] for o in options]
            idx = self._index[key] = BM25Okapi(corpus, k1=self.k1, b=self.b)
        return idx

    def scores(self, text: str, options: list[RouteOption]) -> list[tuple[str, float]]:
        query = tokenize(text)
        if not query or not options:
            return []
        raw = self._bm25(options).get_scores(query)
        return sorted(((o.id, float(s)) for o, s in zip(options, raw, strict=True)),
                      key=lambda kv: -kv[1])

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        ranked = self.scores(inp.message, options)
        if not ranked or ranked[0][1] <= 0:
            return abstain(self.name)
        s1 = ranked[0][1]
        s2 = ranked[1][1] if len(ranked) > 1 else 0.0
        return RouteDecision(
            choice=ranked[0][0],
            confidence=clamp01((s1 - max(s2, 0.0)) / s1),
            candidates=[(k, round(v, 4)) for k, v in ranked],
            strategy=self.name,
        )
