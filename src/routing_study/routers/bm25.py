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
- Index (`index`): `option` = one document per option (above); `utterance` = one document per
  catalog utterance (each example, each description sentence without the PARAMETERS line, the
  keywords), option score = `max` or `topk_sum` (sum of its best `agg_k`) over its utterances.
  With 4-9 options the per-option corpus makes IDF degenerate; ~30-70 utterances do not.
- Analyzer (`analyzer`): `word` tokens or `char` n-grams (`ngram_min`..`ngram_max`, inside
  word boundaries; robust to typos/informal spellings). `fold_accents` switches accent folding.
- Expansion (deterministic, catalog only, no LLM): `shots` adds the catalog example messages
  resolved to the option (a skill's tool examples), `quotes` the quoted WHEN TO USE phrases.
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
    char_ngrams,
    clamp01,
    description_quotes,
    option_utterances,
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
        index: Literal["option", "utterance"] = "option",
        aggregate: Literal["max", "topk_sum"] = "max",
        agg_k: int = 2,
        analyzer: Literal["word", "char"] = "word",
        ngram_min: int = 3,
        ngram_max: int = 5,
        fold_accents: bool = True,
        shots: bool = False,
        quotes: bool = False,
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
        self.index = index
        self.aggregate = aggregate
        self.agg_k = agg_k
        self.analyzer = analyzer
        self.ngram_min = ngram_min
        self.ngram_max = ngram_max
        self.fold_accents = fold_accents
        self.shots = shots
        self.quotes = quotes
        # options key -> (index, owner option position of each document)
        self._index: dict[tuple[str, ...], tuple[BM25Okapi | BM25L, list[int]]] = {}

    def _tok(self, text: str) -> list[str]:
        if self.analyzer == "char":
            return char_ngrams(text, self.ngram_min, self.ngram_max, self.fold_accents)
        return tokenize(text, self.stemmer, self.stopwords, self.prefix_len, self.fold_accents)

    def _new_index(self, corpus: list[list[str]]) -> BM25Okapi | BM25L:
        if self.variant == "l":
            return BM25L(corpus, k1=self.k1, b=self.b, delta=self.delta)
        return BM25Okapi(corpus, k1=self.k1, b=self.b)

    def _document(self, opt: RouteOption) -> list[str]:
        doc = [t for f in FIELDS for t in self._tok(_field_text(opt, f)) * self.field_repeats[f]]
        extra = [
            *(t for t in opt.shots if self.shots and t not in opt.examples),
            *(description_quotes(opt.description) if self.quotes else []),
        ]
        for text in extra:
            doc += self._tok(text) * self.field_repeats["examples"]
        return doc or ["_"]

    def _bm25(self, options: list[RouteOption]) -> tuple[BM25Okapi | BM25L, list[int]]:
        key = tuple(o.model_dump_json() + "\x00" + "\x00".join(o.shots) for o in options)
        hit = self._index.get(key)
        if hit is None:
            if self.index == "utterance":
                docs: list[list[str]] = []
                owner: list[int] = []
                for i, o in enumerate(options):
                    for text in option_utterances(o, shots=self.shots, quotes=self.quotes):
                        docs.append(self._tok(text) or ["_"])
                        owner.append(i)
            else:
                docs = [self._document(o) for o in options]
                owner = list(range(len(options)))
            hit = self._index[key] = (self._new_index(docs), owner)
        return hit

    def _raw(self, text: str, options: list[RouteOption]) -> list[float]:
        query = self._tok(text)
        if not query:
            return [0.0] * len(options)
        idx, owner = self._bm25(options)
        doc_scores = [float(s) for s in idx.get_scores(query)]
        if self.index == "option":
            return doc_scores
        per: list[list[float]] = [[] for _ in options]
        for i, s in zip(owner, doc_scores, strict=True):
            per[i].append(s)
        if self.aggregate == "max":
            return [max(v, default=0.0) for v in per]
        return [sum(sorted(v, reverse=True)[: self.agg_k]) for v in per]

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
