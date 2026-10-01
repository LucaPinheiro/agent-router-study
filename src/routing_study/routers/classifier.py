"""Learned classifier router ("open Jev replica"): a calibrated linear model per stage, trained
on CATALOG text only (no dataset text), fitted on the fly per option set and kept in memory.

Training utterances per option = `option_utterances`: examples, description sentences (without
PARAMETERS), keywords, + `shots` (a skill's tool examples) and `quotes` (WHEN TO USE quotes).
- model `tfidf_lr`: TF-IDF word (1..`word_ngrams`) and/or char_wb (`char_min`..`char_max`)
  n-grams over accent-folded text -> multinomial logistic regression (C, balanced classes).
- model `probe`: linear probe = the same logistic regression on frozen embedding vectors of
  the utterances (the `embedding` strategy's model and vector cache). The query is embedded
  with the embedder's query instruction when `probe_instruction` (else as a document, like the
  training utterances).
History: p = normalise(p(message) + history_weight * p(last `history_turns` messages)).
Raw confidence = p(top); the level's calibration map (fitted on dev folds) turns it into
P(correct). Deterministic (lbfgs, fixed data order).
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion

from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput
from routing_study.routers.calibration import Calibration
from routing_study.routers.common import (
    BaseRouter,
    abstain,
    clamp01,
    normalize,
    option_utterances,
    turns_text,
)
from routing_study.routers.embedding import EmbeddingRouter

ClassifierModel = Literal["tfidf_lr", "probe"]
Features = Literal["word", "char", "word+char"]


class ClassifierRouter(BaseRouter):
    name: ClassVar[str] = "classifier"

    def __init__(
        self,
        *,
        model: ClassifierModel = "tfidf_lr",
        features: Features = "word+char",
        word_ngrams: int = 2,
        char_min: int = 2,
        char_max: int = 5,
        c: float = 10.0,
        shots: bool = True,
        quotes: bool = True,
        description: bool = True,
        history_turns: int = 0,
        history_weight: float = 0.5,
        probe_instruction: bool = False,
        embedding: EmbeddingRouter | None = None,
        calibration: dict[str, Calibration] | None = None,
    ) -> None:
        super().__init__(cache=None, calibration=calibration)
        if model == "probe" and embedding is None:
            raise ValueError("classifier model 'probe' needs the embedding strategy configured")
        self.model_kind: ClassifierModel = model
        self.features: Features = features
        self.word_ngrams = word_ngrams
        self.char_min = char_min
        self.char_max = char_max
        self.c = c
        self.shots = shots
        self.quotes = quotes
        self.description = description
        self.history_turns = history_turns
        self.history_weight = history_weight
        self.probe_instruction = probe_instruction
        self.embedding = embedding
        self._fitted: dict[tuple[str, ...], tuple[Any, LogisticRegression, list[str]]] = {}

    @property
    def model(self) -> str | None:
        return self.embedding.model if self.model_kind == "probe" and self.embedding else None

    def training_set(self, options: list[RouteOption]) -> tuple[list[str], list[str]]:
        texts: list[str] = []
        labels: list[str] = []
        for o in options:
            for t in option_utterances(
                o, shots=self.shots, quotes=self.quotes, description=self.description
            ):
                texts.append(t)
                labels.append(o.id)
        return texts, labels

    def _vectorizer(self) -> Any:
        parts: list[tuple[str, TfidfVectorizer]] = []
        if self.features in ("word", "word+char"):
            parts.append(
                (
                    "word",
                    TfidfVectorizer(
                        preprocessor=normalize,
                        ngram_range=(1, self.word_ngrams),
                        sublinear_tf=True,
                    ),
                )
            )
        if self.features in ("char", "word+char"):
            parts.append(
                (
                    "char",
                    TfidfVectorizer(
                        preprocessor=normalize,
                        analyzer="char_wb",
                        ngram_range=(self.char_min, self.char_max),
                        sublinear_tf=True,
                    ),
                )
            )
        return FeatureUnion(parts)

    async def _fit(self, options: list[RouteOption]) -> tuple[Any, LogisticRegression, list[str]]:
        key = tuple(o.model_dump_json() + "\x00" + "\x00".join(o.shots) for o in options)
        hit = self._fitted.get(key)
        if hit is not None:
            return hit
        texts, labels = self.training_set(options)
        if self.model_kind == "probe":
            assert self.embedding is not None
            x, _ = await self.embedding.text_vectors(texts)
            vec = None
        else:
            vec = self._vectorizer()
            x = vec.fit_transform(texts)
        clf = LogisticRegression(C=self.c, class_weight="balanced", max_iter=5000)
        clf.fit(x, labels)
        out = (vec, clf, [str(c) for c in clf.classes_])
        self._fitted[key] = out
        return out

    async def _proba(self, text: str, vec: Any, clf: LogisticRegression) -> np.ndarray:
        if self.model_kind == "probe":
            assert self.embedding is not None
            if self.probe_instruction:
                qv, _ = await self.embedding.embed_query(RoutingInput(message=text, level="skill"))
                x = qv[None, :]
            else:
                x, _ = await self.embedding.text_vectors([text])
        else:
            x = vec.transform([text])
        return clf.predict_proba(x)[0]

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        if not options or not inp.message.strip():
            return abstain(self.name)
        if len(options) == 1:
            return RouteDecision(
                choice=options[0].id,
                confidence=1.0,
                candidates=[(options[0].id, 1.0)],
                strategy=self.name,
            )
        vec, clf, classes = await self._fit(options)
        p = await self._proba(inp.message, vec, clf)
        past = turns_text(inp, self.history_turns)
        if past and self.history_weight > 0:
            p = p + self.history_weight * await self._proba(past, vec, clf)
            p = p / p.sum()
        order = np.argsort(-p, kind="stable")
        return RouteDecision(
            choice=classes[int(order[0])],
            confidence=clamp01(float(p[order[0]])),
            candidates=[(classes[int(i)], round(float(p[i]), 4)) for i in order],
            strategy=self.name,
        )
