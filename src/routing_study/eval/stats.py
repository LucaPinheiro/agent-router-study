"""Uncertainty for the published tables (review L4): paired cluster bootstrap and McNemar.

- Bootstrap: resample case ids with replacement (every repetition of a case moves together),
  fixed seed, `BOOT_N` resamples, percentile 95% interval. Configs compared on the same sorted
  case-id set draw the SAME resamples, so their intervals are paired.
- McNemar: exact two-sided binomial test on the discordant (case_id, rep) pairs of two configs.
  Repetitions of one case are not independent, so with reps > 1 the p-value is optimistic.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from math import comb

import numpy as np

BOOT_SEED = 20260930
BOOT_N = 10_000


def _resamples(n_keys: int, n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, n_keys, size=(n, n_keys))


def bootstrap_mean(
    groups: Mapping[Hashable, Sequence[float]], *, n: int = BOOT_N, seed: int = BOOT_SEED
) -> tuple[float, float, float] | None:
    """(point, lo, hi) of the row mean, resampling the groups (case ids). None when empty."""
    keys = sorted(groups, key=str)
    if not keys:
        return None
    sums = np.array([float(sum(groups[k])) for k in keys])
    counts = np.array([len(groups[k]) for k in keys], dtype=float)
    idx = _resamples(len(keys), n, seed)
    means = sums[idx].sum(axis=1) / np.maximum(counts[idx].sum(axis=1), 1.0)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(sums.sum() / counts.sum()), float(lo), float(hi)


def bootstrap_stat(
    groups: Mapping[Hashable, Sequence[float]],
    stat: Callable[[np.ndarray], float],
    *,
    n: int = BOOT_N,
    seed: int = BOOT_SEED,
) -> tuple[float, float, float] | None:
    """(point, lo, hi) of any statistic of the pooled rows (e.g. the median latency)."""
    keys = sorted(groups, key=str)
    if not keys:
        return None
    arrays = [np.asarray(groups[k], dtype=float) for k in keys]
    idx = _resamples(len(keys), n, seed)
    values = np.array([stat(np.concatenate([arrays[i] for i in row])) for row in idx])
    lo, hi = np.percentile(values, [2.5, 97.5])
    return float(stat(np.concatenate(arrays))), float(lo), float(hi)


def mcnemar(
    a: Mapping[Hashable, float], b: Mapping[Hashable, float]
) -> tuple[int, int, int, float] | None:
    """(n_shared, a-only correct, b-only correct, exact two-sided p) over the keys both
    configs scored. None when they share no key."""
    shared = a.keys() & b.keys()
    if not shared:
        return None
    a_only = sum(1 for k in shared if a[k] >= 0.5 > b[k])
    b_only = sum(1 for k in shared if b[k] >= 0.5 > a[k])
    m = a_only + b_only
    if m == 0:
        return len(shared), 0, 0, 1.0
    tail = sum(comb(m, i) for i in range(min(a_only, b_only) + 1)) / 2**m
    return len(shared), a_only, b_only, min(1.0, 2 * tail)


def fmt_ci(ci: tuple[float, float, float] | None, *, scale: float = 100.0, digits: int = 1) -> str:
    if ci is None:
        return "-"
    p, lo, hi = (scale * x for x in ci)
    return f"{p:.{digits}f} [{lo:.{digits}f}, {hi:.{digits}f}]"
