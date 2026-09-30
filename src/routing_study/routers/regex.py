"""Regex-first router: weighted YAML patterns per option id; highest weight sum wins.

Confidence = strength * (0.5 + 0.5 * separation):
- strength   = min(1, top_score / full_score)   (0 without any match)
- separation = (top1 - top2) / top1              (halved confidence on a tie)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import BaseModel, Field

from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput
from routing_study.routers.common import (
    BaseRouter,
    abstain,
    clamp01,
    normalize,
    strip_accents,
)


class RegexRule(BaseModel):
    pattern: str
    weight: float = Field(default=1.0, gt=0.0)


class RegexRules(BaseModel):
    full_score: float = Field(default=1.0, gt=0.0)
    rules: dict[str, list[RegexRule]] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> RegexRules:
        return cls.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})


class RegexRouter(BaseRouter):
    name: ClassVar[str] = "regex"

    def __init__(self, rules: RegexRules) -> None:
        super().__init__(cache=None)
        self.rules = rules
        # Input is lowercased + accent-stripped; patterns are accent-stripped (case kept so
        # escapes like \S survive) and compiled case-insensitive.
        self._compiled = {
            opt: [(re.compile(strip_accents(r.pattern), re.IGNORECASE), r.weight) for r in rs]
            for opt, rs in rules.rules.items()
        }

    @classmethod
    def from_path(cls, path: str | Path) -> RegexRouter:
        return cls(RegexRules.load(path))

    def score(self, text: str, options: list[RouteOption]) -> dict[str, float]:
        norm = normalize(text)
        return {
            o.id: sum(w for rx, w in self._compiled.get(o.id, []) if rx.search(norm))
            for o in options
        }

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        scores = self.score(inp.message, options)
        ranked = sorted(((k, v) for k, v in scores.items() if v > 0), key=lambda kv: -kv[1])
        if not ranked:
            return abstain(self.name, matched=0)
        top_id, s1 = ranked[0]
        s2 = ranked[1][1] if len(ranked) > 1 else 0.0
        strength = min(1.0, s1 / self.rules.full_score)
        separation = (s1 - s2) / s1
        return RouteDecision(
            choice=top_id,
            confidence=clamp01(strength * (0.5 + 0.5 * separation)),
            candidates=[(k, round(v, 4)) for k, v in ranked],
            strategy=self.name,
            usage={"matched": len(ranked)},
        )
