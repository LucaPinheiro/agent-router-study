"""Regex-first router: weighted YAML patterns per option id; highest weight sum wins.

A negative weight is a suppressor (e.g. a policy question lowers the action tools). With
`history_turns` > 0 the score is score(message) + history_weight * score(last turns), so a
short follow-up inherits the conversation's intent.

Raw confidence = strength * (0.5 + 0.5 * separation), then the level's calibration, if set:
- strength   = min(1, top_score / full_score)   (0 without any match)
- separation = (top1 - top2) / top1              (halved confidence on a tie)
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput
from routing_study.routers.calibration import Calibration
from routing_study.routers.common import (
    BaseRouter,
    abstain,
    clamp01,
    normalize,
    strip_accents,
    turns_text,
)


class RegexRule(BaseModel):
    pattern: str
    weight: float = Field(default=1.0, ge=-1.0, le=1.0)

    @field_validator("weight")
    @classmethod
    def _nonzero(cls, v: float) -> float:
        if v == 0:
            raise ValueError("weight 0 never changes a score; remove the rule")
        return v


_DEF_REF = re.compile(r"\{\{(\w+)\}\}")


class RegexRules(BaseModel):
    full_score: float = Field(default=1.0, gt=0.0)
    # named vocabulary fragments, referenced as {{NAME}} in patterns (and in later defs)
    defs: dict[str, str] = Field(default_factory=dict)
    rules: dict[str, list[RegexRule]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _expand_defs(self) -> RegexRules:
        """Resolve {{NAME}} (as a non-capturing group) in defs, in order, then in rules."""
        resolved: dict[str, str] = {}

        def expand(pattern: str) -> str:
            def sub(m: re.Match[str]) -> str:
                if m.group(1) not in resolved:
                    raise ValueError(f"undefined (or later) regex def {{{{{m.group(1)}}}}}")
                return f"(?:{resolved[m.group(1)]})"

            return _DEF_REF.sub(sub, pattern)

        for name, frag in self.defs.items():
            resolved[name] = expand(frag)
        for rs in self.rules.values():
            for r in rs:
                r.pattern = expand(r.pattern)
        return self

    @classmethod
    def load(cls, path: str | Path, overlays: Sequence[str | Path] = ()) -> RegexRules:
        """`path` plus `overlays` merged in order: overlay `defs` are appended (a name already
        defined is an error) and overlay rules are appended to the option's list. An overlay
        holds only `defs` and `rules` (`full_score` stays the base's)."""

        def read(p: str | Path) -> dict[str, Any]:
            return yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}

        data = read(path)
        data.setdefault("defs", {})
        data.setdefault("rules", {})
        for p in overlays:
            extra = read(p)
            if bad := set(extra) - {"defs", "rules"}:
                raise ValueError(f"{p}: an overlay holds only defs/rules (got {sorted(bad)})")
            if dup := set(extra.get("defs") or {}) & set(data["defs"]):
                raise ValueError(f"{p}: def(s) already defined {sorted(dup)}")
            data["defs"].update(extra.get("defs") or {})
            for opt, rs in (extra.get("rules") or {}).items():
                data["rules"][opt] = [*(data["rules"].get(opt) or []), *rs]
        return cls.model_validate(data)


class RegexRouter(BaseRouter):
    name: ClassVar[str] = "regex"

    def __init__(
        self,
        rules: RegexRules,
        calibration: dict[str, Calibration] | None = None,
        *,
        history_turns: int = 0,
        history_weight: float = 0.5,
    ) -> None:
        super().__init__(cache=None, calibration=calibration)
        self.rules = rules
        self.history_turns = history_turns
        self.history_weight = history_weight
        # Input is lowercased + accent-stripped; patterns are accent-stripped (case kept so
        # escapes like \S survive) and compiled case-insensitive.
        self._compiled = {
            opt: [(re.compile(strip_accents(r.pattern), re.IGNORECASE), r.weight) for r in rs]
            for opt, rs in rules.rules.items()
        }

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        calibration: dict[str, Calibration] | None = None,
        overlays: list[str] | None = None,
        **kwargs: Any,
    ) -> RegexRouter:
        return cls(RegexRules.load(path, overlays or []), calibration, **kwargs)

    def score(self, text: str, options: list[RouteOption]) -> dict[str, float]:
        norm = normalize(text)
        return {
            # rounded: float sums (0.6 + 0.3 = 0.8999…) must not miss full_score / thresholds
            o.id: round(sum(w for rx, w in self._compiled.get(o.id, []) if rx.search(norm)), 6)
            for o in options
        }

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        scores = self.score(inp.message, options)
        history = turns_text(inp, self.history_turns)
        if history and self.history_weight > 0:
            past = self.score(history, options)
            scores = {k: round(v + self.history_weight * past[k], 6) for k, v in scores.items()}
        ranked = sorted(((k, v) for k, v in scores.items() if v > 0), key=lambda kv: -kv[1])
        if not ranked:
            return abstain(self.name, matched=0)
        top_id, s1 = ranked[0]
        s2 = ranked[1][1] if len(ranked) > 1 else 0.0
        strength = min(1.0, s1 / self.rules.full_score)
        separation = (s1 - s2) / s1
        return RouteDecision(
            choice=top_id,
            confidence=clamp01(round(strength * (0.5 + 0.5 * separation), 6)),
            candidates=[(k, round(v, 4)) for k, v in ranked],
            strategy=self.name,
            usage={"matched": len(ranked)},
        )
