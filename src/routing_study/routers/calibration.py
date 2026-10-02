"""Confidence calibration: raw router score -> P(choice correct), fitted offline on dev folds.

`Calibration` is a monotone piecewise-linear map stored in the experiment config (so it is part
of the config hash); `fit_isotonic` fits one with pool-adjacent-violators (PAV) and a Beta(1,1)
prior per block, so a small all-correct block maps to (n+1)/(n+2), never to exactly 1.0.
A raw confidence of 0 is a "do not trust" sentinel and stays 0 after calibration.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Calibration(BaseModel):
    """Knots of a non-decreasing map; linear between knots, flat outside them."""

    model_config = ConfigDict(extra="forbid")

    x: list[float] = Field(min_length=1)
    y: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def _monotone(self) -> Calibration:
        if len(self.x) != len(self.y):
            raise ValueError("calibration: x and y must have the same length")
        if any(b < a for a, b in zip(self.x, self.x[1:], strict=False)):
            raise ValueError("calibration: x must be non-decreasing")
        if any(b < a for a, b in zip(self.y, self.y[1:], strict=False)):
            raise ValueError("calibration: y must be non-decreasing")
        if any(not 0.0 <= v <= 1.0 for v in self.y):
            raise ValueError("calibration: y must be in [0, 1]")
        return self

    def __call__(self, raw: float) -> float:
        """Sentinel rule: a raw confidence of 0 (or below) means "do not trust this choice"
        (missing/invalid reported confidence, no logprobs) and maps to 0, never to the map's
        floor; every other value is interpolated."""
        if raw <= 0.0:
            return 0.0
        return float(np.interp(raw, self.x, self.y))


def fit_isotonic(scores: Sequence[float], labels: Sequence[float]) -> Calibration:
    """Isotonic regression of `labels` (0/1) on `scores`; one knot per PAV block, placed at
    the block's mean score. Tied scores always share a block."""
    if len(scores) != len(labels) or not scores:
        raise ValueError("fit_isotonic: need equally long, non-empty scores and labels")
    xs = np.asarray(scores, dtype=float)
    ys = np.asarray(labels, dtype=float)
    # blocks: [sum_x, sum_y, n]; one initial block per distinct score, then PAV merges
    blocks: list[list[float]] = []
    for x in np.unique(xs):
        mask = xs == x
        blocks.append([float(xs[mask].sum()), float(ys[mask].sum()), float(mask.sum())])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] >= blocks[-1][1] / blocks[-1][2]:
            sx, sy, n = blocks.pop()
            blocks[-1][0] += sx
            blocks[-1][1] += sy
            blocks[-1][2] += n
    knots_x = [round(sx / n, 6) for sx, _, n in blocks]
    smoothed = np.maximum.accumulate([(sy + 1.0) / (n + 2.0) for _, sy, n in blocks])
    return Calibration(x=knots_x, y=[round(float(v), 6) for v in smoothed])


def ece(confidences: Sequence[float], correct: Sequence[float], bins: int = 10) -> float:
    """Expected calibration error with equal-width bins (weighted |accuracy - confidence|)."""
    if not confidences:
        return 0.0
    conf = np.asarray(confidences, dtype=float)
    ok = np.asarray(correct, dtype=float)
    idx = np.minimum((conf * bins).astype(int), bins - 1)
    total = 0.0
    for b in range(bins):
        mask = idx == b
        if mask.any():
            total += mask.sum() * abs(ok[mask].mean() - conf[mask].mean())
    return float(total / len(conf))


def brier(confidences: Sequence[float], correct: Sequence[float]) -> float:
    """Mean squared error between confidence and the 0/1 outcome."""
    if not confidences:
        return 0.0
    conf = np.asarray(confidences, dtype=float)
    ok = np.asarray(correct, dtype=float)
    return float(np.mean((conf - ok) ** 2))


def _logistic_fit(
    x: np.ndarray, y: np.ndarray, l2: float, iters: int = 100
) -> tuple[np.ndarray, float]:
    """L2-penalised logistic regression (bias unpenalised) by Newton-Raphson; deterministic.
    x: (n, d), y: (n,) in {0, 1}. Returns (weights, bias)."""
    n, d = x.shape
    xb = np.hstack([x, np.ones((n, 1))])
    w = np.zeros(d + 1)
    reg = np.full(d + 1, l2)
    reg[-1] = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(xb @ w, -30, 30)))
        grad = xb.T @ (p - y) + reg * w
        hess = (xb * (p * (1 - p))[:, None]).T @ xb + np.diag(reg + 1e-9)
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w[:-1], float(w[-1])


def fit_platt(
    scores: Sequence[float], labels: Sequence[float], knots: int = 21, l2: float = 1e-3
) -> Calibration:
    """Platt scaling (sigmoid a * raw + b, fitted by logistic regression) stored as a
    `Calibration` with `knots` points evenly spread over the observed raw range, so it is
    applied (and hashed) like an isotonic map. A non-increasing fit (a <= 0) is replaced by
    the constant base rate. Smoother than isotonic at small n (few knots, no steps)."""
    if len(scores) != len(labels) or not scores:
        raise ValueError("fit_platt: need equally long, non-empty scores and labels")
    xs = np.asarray(scores, dtype=float)
    ys = np.asarray(labels, dtype=float)
    lo, hi = float(xs.min()), float(xs.max())
    grid = np.linspace(lo, hi, knots) if hi > lo else np.array([lo])
    if len(np.unique(ys)) < 2:
        rate = (ys.sum() + 1.0) / (len(ys) + 2.0)
        return Calibration(x=[round(float(g), 6) for g in grid], y=[round(rate, 6)] * len(grid))
    w, b = _logistic_fit(xs[:, None], ys, l2)
    if w[0] <= 0:
        rate = float(ys.mean())
        vals = np.full(len(grid), rate)
    else:
        vals = 1.0 / (1.0 + np.exp(-(w[0] * grid + b)))
    vals = np.maximum.accumulate(np.clip(vals, 0.0, 1.0))
    return Calibration(x=[round(float(g), 6) for g in grid], y=[round(float(v), 6) for v in vals])


class LogisticModel(BaseModel):
    """A tiny logistic model over named features (the hybrid stacker, the learned cascade
    deferral scorer). Stored in configs, so part of the config hash."""

    model_config = ConfigDict(extra="forbid")

    features: list[str] = Field(min_length=1)
    weights: list[float] = Field(min_length=1)
    bias: float = 0.0

    @model_validator(mode="after")
    def _same_length(self) -> LogisticModel:
        if len(self.features) != len(self.weights):
            raise ValueError("logistic model: features and weights must have the same length")
        return self

    def __call__(self, feats: dict[str, float]) -> float:
        z = self.bias + sum(
            w * float(feats.get(f, 0.0)) for f, w in zip(self.features, self.weights, strict=True)
        )
        return float(1.0 / (1.0 + np.exp(-np.clip(z, -30, 30))))


def fit_logistic(
    rows: Sequence[dict[str, float]],
    labels: Sequence[float],
    features: Sequence[str],
    l2: float = 1.0,
) -> LogisticModel:
    """Fit a `LogisticModel` on feature dicts (missing feature = 0); L2 on the weights."""
    if len(rows) != len(labels) or not rows:
        raise ValueError("fit_logistic: need equally long, non-empty rows and labels")
    x = np.array([[float(r.get(f, 0.0)) for f in features] for r in rows])
    y = np.asarray(labels, dtype=float)
    if len(np.unique(y)) < 2:
        rate = (y.sum() + 1.0) / (len(y) + 2.0)
        return LogisticModel(
            features=list(features),
            weights=[0.0] * len(features),
            bias=float(np.log(rate / (1 - rate))),
        )
    w, b = _logistic_fit(x, y, l2)
    return LogisticModel(
        features=list(features), weights=[round(float(v), 6) for v in w], bias=round(b, 6)
    )
