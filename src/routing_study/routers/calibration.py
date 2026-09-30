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
