"""BM25 router (local) over the catalog text of each option (description, examples, keywords).

- Variant: `okapi` (original) or `l` = rank_bm25's `BM25L` class (Lv & Zhai 2011 length
  normalization with `delta`, and rank_bm25's own IDF log((N+1)/(n+0.5)); not a separate
  implementation, so results are rank_bm25's variant as shipped). With 4-8 option documents
  Okapi's IDF is 0 for a term in exactly half of them and floored for more, so
  shared-but-discriminative words ("devolver" in a skill and in `__global__`) score nothing;
  that BM25L IDF stays positive.
- Text: accent-free tokens, pt-BR stopwords (`basic` | `extended` = + courtesy/filler words),
  optional stemming (`light` suffix stripper | `prefix` truncation).
- Fields: one document per option = description + examples + keywords, each field's tokens
  repeated `field_repeats[field]` times (BM25F-style term-frequency weighting; 1/1/1 is the
  original document, 0 drops the field).
- History: score(message) + history_weight * score(last `history_turns` messages), so a short
  follow-up ("sim, faz isso") inherits the intent of the conversation.
Confidence = normalized margin (top1 - top2) / top1 (then the level's calibration, if set);
abstains when nothing scores.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from rank_bm25 import BM25L, BM25Okapi

from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput
from routing_study.routers.calibration import Calibration
from routing_study.routers.common import (
    BaseRouter,
    Stemmer,
    Stopwords,
    abstain,
    clamp01,
    tokenize,
    turns_text,
)

FIELDS = ("description", "examples", "keywords")


def _field_text(opt: RouteOption, field: str) -> str:
    if field == "description":
        return opt.description
    return " ".join(getattr(opt, field))


class BM25Router(BaseRouter):
    name: ClassVar[str] = "bm25"

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        calibration: dict[str, Calibration] | None = None,
        *,
        stemmer: Stemmer = "none",
        prefix_len: int = 5,
        stopwords: Stopwords = "basic",
        field_repeats: dict[str, int] | None = None,
        history_turns: int = 0,
        history_weight: float = 0.5,
        variant: Literal["okapi", "l"] = "okapi",
        delta: float = 0.5,
    ) -> None:
        super().__init__(cache=None, calibration=calibration)
        self.k1 = k1
        self.b = b
        self.stemmer: Stemmer = stemmer
        self.prefix_len = prefix_len
        self.stopwords: Stopwords = stopwords
        self.field_repeats = {f: 1 for f in FIELDS} | (field_repeats or {})
        self.history_turns = history_turns
        self.history_weight = history_weight
        self.variant = variant
        self.delta = delta
        self._index: dict[tuple[str, ...], BM25Okapi | BM25L] = {}

    def _tok(self, text: str) -> list[str]:
        return tokenize(text, self.stemmer, self.stopwords, self.prefix_len)

    def _new_index(self, corpus: list[list[str]]) -> BM25Okapi | BM25L:
        if self.variant == "l":
            return BM25L(corpus, k1=self.k1, b=self.b, delta=self.delta)
        return BM25Okapi(corpus, k1=self.k1, b=self.b)

    def _document(self, opt: RouteOption) -> list[str]:
        return [
            t for f in FIELDS for t in self._tok(_field_text(opt, f)) * self.field_repeats[f]
        ] or ["_"]

    def _bm25(self, options: list[RouteOption]) -> BM25Okapi | BM25L:
        key = tuple(o.model_dump_json() for o in options)
        idx = self._index.get(key)
        if idx is None:
            idx = self._index[key] = self._new_index([self._document(o) for o in options])
        return idx

    def _raw(self, text: str, options: list[RouteOption]) -> list[float]:
        query = self._tok(text)
        if not query:
            return [0.0] * len(options)
        return [float(s) for s in self._bm25(options).get_scores(query)]

    def scores(
        self, text: str, options: list[RouteOption], history: str = ""
    ) -> list[tuple[str, float]]:
        if not options:
            return []
        total = self._raw(text, options)
        if history and self.history_weight > 0:
            past = self._raw(history, options)
            total = [s + self.history_weight * p for s, p in zip(total, past, strict=True)]
        if not any(total):
            return []
        return sorted(
            ((o.id, s) for o, s in zip(options, total, strict=True)), key=lambda kv: -kv[1]
        )

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        ranked = self.scores(inp.message, options, turns_text(inp, self.history_turns))
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
