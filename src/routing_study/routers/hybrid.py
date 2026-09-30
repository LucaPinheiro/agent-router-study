"""Hybrid router: Reciprocal Rank Fusion of BM25 + dense embeddings.

RRF(o) = sum_r 1 / (k + rank_r(o)) picks the choice. Raw RRF margins are tiny with k=60
(~0.02 for a unanimous win), so confidence is the agreement-weighted mean of the sub-router
confidences: mean_r(conf_r if top1_r == fused top1 else 0). Abstaining sub-routers add nothing.
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput
from routing_study.routers.bm25 import BM25Router
from routing_study.routers.common import BaseRouter, abstain, clamp01
from routing_study.routers.embedding import EmbeddingRouter


class HybridRouter(BaseRouter):
    name: ClassVar[str] = "hybrid"
    paid: ClassVar[bool] = True

    def __init__(self, bm25: BM25Router, embedding: EmbeddingRouter, rrf_k: int = 60) -> None:
        super().__init__(cache=None)
        self.bm25 = bm25
        self.embedding = embedding
        self.rrf_k = rrf_k

    @property
    def model(self) -> str | None:
        return self.embedding.model

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        # Use the undecorated paths: the sub-decisions are inputs, not separate spans.
        lex, dense = await asyncio.gather(
            self.bm25._route(inp, options), self.embedding._route(inp, options)
        )
        fused: dict[str, float] = {}
        for d in (lex, dense):
            if d.choice is None:
                continue
            for rank, (oid, _) in enumerate(d.candidates, start=1):
                fused[oid] = fused.get(oid, 0.0) + 1.0 / (self.rrf_k + rank)
        usage = {
            **{k: v for k, v in dense.usage.items()},
            "bm25_choice": lex.choice,
            "embedding_choice": dense.choice,
        }
        if not fused:
            return abstain(self.name, **usage).model_copy(update={"cost_usd": dense.cost_usd})
        ranked = sorted(fused.items(), key=lambda kv: -kv[1])
        top = ranked[0][0]
        agree = [d.confidence if d.choice == top else 0.0 for d in (lex, dense)]
        return RouteDecision(
            choice=top,
            confidence=clamp01(sum(agree) / len(agree)),
            candidates=[(k, round(v, 6)) for k, v in ranked],
            strategy=self.name,
            cost_usd=dense.cost_usd,
            usage=usage,
        )
