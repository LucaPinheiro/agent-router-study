"""Hybrid router: fusion of cheap routers (default members BM25 + dense embeddings).

Every member decision becomes a distribution over the options (`option_distribution`): the
member's top choice gets its CALIBRATED confidence c, the other options share 1 - c in
proportion to their (min-shifted) raw candidate scores; an abstaining member is uniform.

- fusion `convex` (default): fused(o) = sum_r w_r * p_r(o), weights normalised to 1. With two
  members `alpha` is the weight of the first (semantic-router convention for
  [bm25, embedding]: alpha 0 = dense only, 1 = sparse only); `weights` overrides it. Raw
  confidence = fused(top). Alpha is chosen by CV on dev (scripts/analysis/tune_router.py).
- fusion `stacker`: a per-level logistic model (`LogisticModel`, fitted on dev folds by
  scripts/analysis/fit_hybrid.py) scores each option from `stack_features` (each member's
  p_r(o) and top-1 flag, the share of members whose top is o, unanimity); choice = argmax,
  raw confidence = the model's P(correct) of the top option.
- fusion `rrf` (documented baseline): RRF(o) = sum_r 1 / (k + rank_r(o)); with 2 rankers over
  3-9 options it is almost a fixed rule (rrf_k does not matter). Raw confidence = the
  agreement-weighted mean of the member confidences.
The raw confidence then goes through the hybrid's own calibration map (if set).

`deferral_features` / `fit_deferral`: the learned deferral scorer for cascades (FrugalGPT-style:
a logistic model on step confidences, margins and agreement between the cheap routers) that
the cascade calibrator can call on recorded shadow decisions.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Literal

from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput
from routing_study.routers.calibration import Calibration, LogisticModel, fit_logistic
from routing_study.routers.common import BaseRouter, abstain, clamp01

Fusion = Literal["rrf", "convex", "stacker"]


def option_distribution(
    d: RouteDecision | Mapping[str, Any], ids: Sequence[str]
) -> dict[str, float]:
    """A member decision as a distribution over `ids` (see module docstring)."""
    choice = d["choice"] if isinstance(d, Mapping) else d.choice
    conf = float(d["confidence"] if isinstance(d, Mapping) else d.confidence)
    cands = d["candidates"] if isinstance(d, Mapping) else d.candidates
    n = len(ids)
    if not n:
        return {}
    if choice is None or choice not in ids:
        return dict.fromkeys(ids, 1.0 / n)
    if n == 1:
        return {choice: 1.0}
    raw = {str(k): float(v) for k, v in cands}
    rest = [o for o in ids if o != choice]
    vals = [raw.get(o, 0.0) for o in rest]
    lo = min([*vals, 0.0])
    shifted = [v - lo for v in vals]
    total = sum(shifted)
    share = [s / total for s in shifted] if total > 0 else [1.0 / len(rest)] * len(rest)
    conf = clamp01(conf)
    out = {o: (1.0 - conf) * s for o, s in zip(rest, share, strict=True)}
    out[choice] = conf
    return out


def stack_features(
    decisions: Mapping[str, RouteDecision | Mapping[str, Any]], ids: Sequence[str]
) -> dict[str, dict[str, float]]:
    """Per option: p_<member>, top_<member>, agree (share of members whose top is it),
    unanimous (all members chose it)."""
    dists = {m: option_distribution(d, ids) for m, d in decisions.items()}
    tops = {m: (d["choice"] if isinstance(d, Mapping) else d.choice) for m, d in decisions.items()}
    out: dict[str, dict[str, float]] = {}
    for o in ids:
        f: dict[str, float] = {}
        for m in decisions:
            f[f"p_{m}"] = dists[m][o]
            f[f"top_{m}"] = 1.0 if tops[m] == o else 0.0
        votes = sum(1 for m in decisions if tops[m] == o)
        f["agree"] = votes / len(decisions) if decisions else 0.0
        f["unanimous"] = 1.0 if decisions and votes == len(decisions) else 0.0
        out[o] = f
    return out


def stack_feature_names(members: Sequence[str]) -> list[str]:
    return [*(f"p_{m}" for m in members), *(f"top_{m}" for m in members), "agree", "unanimous"]


# ---------------------------------------------------------------- learned deferral (cascades)


def _get(d: RouteDecision | Mapping[str, Any], key: str) -> Any:
    return d.get(key) if isinstance(d, Mapping) else getattr(d, key)


def deferral_features(
    steps: Mapping[str, RouteDecision | Mapping[str, Any] | None],
    turns: int | None = None,
) -> dict[str, float]:
    """Features of the cheap routers' decisions on one case/stage for a deferral scorer:
    per step conf_<s>, abstain_<s>, margin_<s> (top1 - top2 of its candidate scores,
    min-max scaled per decision); pairwise agree_<a>_<b>; n_choices (distinct non-null
    choices); multi_turn when `turns` is given. Accepts RouteDecisions or their dumps
    (recorded shadow rows)."""
    f: dict[str, float] = {}
    names = list(steps)
    for s in names:
        d = steps[s]
        choice = None if d is None else _get(d, "choice")
        f[f"abstain_{s}"] = 1.0 if choice is None else 0.0
        f[f"conf_{s}"] = 0.0 if choice is None else float(_get(d, "confidence"))  # type: ignore[arg-type]
        vals = [float(v) for _, v in (_get(d, "candidates") or [])] if d is not None else []
        if len(vals) >= 2 and choice is not None:
            span = max(vals) - min(vals)
            top = sorted(vals, reverse=True)
            f[f"margin_{s}"] = (top[0] - top[1]) / span if span > 0 else 0.0
        else:
            f[f"margin_{s}"] = 1.0 if vals and choice is not None else 0.0
    choices = {s: (None if steps[s] is None else _get(steps[s], "choice")) for s in names}  # type: ignore[arg-type]
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            same = choices[a] is not None and choices[a] == choices[b]
            f[f"agree_{a}_{b}"] = 1.0 if same else 0.0
    f["n_choices"] = float(len({c for c in choices.values() if c is not None}))
    if turns is not None:
        f["multi_turn"] = 1.0 if turns > 1 else 0.0
    return f


def fit_deferral(
    rows: Sequence[dict[str, float]], correct: Sequence[float], l2: float = 1.0
) -> LogisticModel:
    """Logistic P(the cheap step's decision is correct) from `deferral_features` rows; a
    cascade defers (escalates) when it is below its threshold."""
    names = sorted({k for r in rows for k in r})
    return fit_logistic(rows, correct, names, l2=l2)


# ---------------------------------------------------------------- router


class HybridRouter(BaseRouter):
    name: ClassVar[str] = "hybrid"
    paid: ClassVar[bool] = True

    def __init__(
        self,
        bm25: BaseRouter,
        embedding: BaseRouter,
        rrf_k: int = 60,
        *,
        fusion: Fusion = "rrf",
        alpha: float = 0.5,
        weights: dict[str, float] | None = None,
        members: dict[str, BaseRouter] | None = None,
        stacker: dict[str, LogisticModel] | None = None,
        calibration: dict[str, Calibration] | None = None,
    ) -> None:
        super().__init__(cache=None, calibration=calibration)
        self.bm25 = bm25
        self.embedding = embedding
        self.rrf_k = rrf_k
        self.fusion: Fusion = fusion
        self.alpha = alpha
        self.members: dict[str, BaseRouter] = members or {"bm25": bm25, "embedding": embedding}
        self.weights = weights or {}
        self.stacker = stacker or {}
        if fusion == "stacker" and not self.stacker:
            raise ValueError("hybrid fusion 'stacker' needs fitted `stacker` models per level")

    @property
    def model(self) -> str | None:
        return getattr(self.members.get("embedding"), "model", None) or getattr(
            self.embedding, "model", None
        )

    def _weights(self) -> dict[str, float]:
        names = list(self.members)
        if self.weights:
            w = {m: float(self.weights.get(m, 0.0)) for m in names}
        elif len(names) == 2:
            w = {names[0]: self.alpha, names[1]: 1.0 - self.alpha}
        else:
            w = dict.fromkeys(names, 1.0)
        total = sum(w.values()) or 1.0
        return {m: v / total for m, v in w.items()}

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        # Use the undecorated paths: the sub-decisions are inputs, not separate spans.
        names = list(self.members)
        subs = await asyncio.gather(*(self.members[m]._route(inp, options) for m in names))
        by = dict(zip(names, subs, strict=True))
        paid = [d for m, d in by.items() if getattr(self.members[m], "paid", False)]
        usage: dict[str, Any] = {}
        for d in paid:
            usage.update(d.usage)
        usage.update({f"{m}_choice": d.choice for m, d in by.items()})
        usage["fusion"] = self.fusion
        # Sub-decisions ran in parallel: latency = the slowest one (original if cached); the
        # paid members decide `cached`, so a cache hit is not counted as billed.
        inherited = {
            "cost_usd": sum(d.cost_usd for d in paid),
            "cached": bool(paid) and all(d.cached for d in paid),
            "latency_ms": max((d.latency_ms for d in subs), default=0.0),
        }
        ids = [o.id for o in options]
        if all(d.choice is None for d in subs) or not ids:
            return abstain(self.name, **usage).model_copy(update=inherited)
        if self.fusion == "rrf":
            fused: dict[str, float] = {}
            for d in subs:
                if d.choice is None:
                    continue
                for rank, (oid, _) in enumerate(d.candidates, start=1):
                    fused[oid] = fused.get(oid, 0.0) + 1.0 / (self.rrf_k + rank)
            ranked = sorted(fused.items(), key=lambda kv: -kv[1])
            top = ranked[0][0]
            agree = [d.confidence if d.choice == top else 0.0 for d in subs]
            conf = sum(agree) / len(agree)
        elif self.fusion == "convex":
            w = self._weights()
            dists = {m: option_distribution(d, ids) for m, d in by.items()}
            fused = {o: sum(w[m] * dists[m][o] for m in names) for o in ids}
            ranked = sorted(fused.items(), key=lambda kv: -kv[1])
            conf = ranked[0][1]
        else:
            model = self.stacker.get(inp.level)
            if model is None:
                raise ValueError(f"hybrid stacker has no model for level {inp.level!r}")
            feats = stack_features(by, ids)
            fused = {o: model(feats[o]) for o in ids}
            ranked = sorted(fused.items(), key=lambda kv: -kv[1])
            conf = ranked[0][1]
        return RouteDecision(
            choice=ranked[0][0],
            confidence=clamp01(conf),
            candidates=[(k, round(v, 6)) for k, v in ranked],
            strategy=self.name,
            usage=usage,
            **inherited,
        )
