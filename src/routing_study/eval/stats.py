"""Uncertainty for the published tables (review L4, B6 / F4). The unit of analysis is the
CASE: repetitions of a case are not independent, so every test and interval of a difference
works on per-case means over reps (`case_means`).

- `bootstrap_mean`: marginal CI; resample case ids with replacement (every repetition of a
  case moves together), fixed seed, `BOOT_N` resamples, percentile interval. Configs compared on
  the same sorted case-id set draw the SAME resamples, so their intervals are paired.
- `paired_delta`: CI of the paired difference Δ = mean(a) - mean(b) over the cases both
  configs scored (per-case means, case ids resampled; 10k, seed 20260930).
- `mcnemar_cases`: exact two-sided McNemar on the per-case MAJORITY (mean > 0.5 is correct;
  a tie at 0.5 counts as not correct). `sign_flip`: two-sided sign-flip permutation test of the
  mean per-case difference (exact up to `EXACT_MAX` non-zero cases, else Monte Carlo, seeded).
- `holm`: Holm step-down adjustment within ONE pre-registered family.
- `non_inferiority` / `tost`: margin tests on the paired bootstrap CI of Δ (non-inferiority:
  lower bound of the two-sided 95% CI = one-sided 97.5% > -margin; TOST equivalence: the
  90% CI inside ±margin).
- `mcnemar`: the legacy exact test on (case_id, rep) pairs; with reps > 1 its p-value is
  optimistic (reps are not independent): kept for audit, never a published test.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from math import comb
from typing import Any

import numpy as np

BOOT_SEED = 20260930
BOOT_N = 10_000
EXACT_MAX = 20  # sign-flip: enumerate all 2^m sign patterns up to this many non-zero cases


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


def case_means(scores: Mapping[Hashable, float]) -> dict[Hashable, float]:
    """case id -> mean over its reps. Keys are (case_id, rep) tuples or already case ids."""
    sums: dict[Hashable, list[float]] = {}
    for k, v in scores.items():
        case = k[0] if isinstance(k, tuple) else k
        sums.setdefault(case, []).append(float(v))
    return {c: sum(v) / len(v) for c, v in sums.items()}


def _paired(
    a: Mapping[Hashable, float], b: Mapping[Hashable, float]
) -> tuple[list[Hashable], np.ndarray, np.ndarray]:
    ca, cb = case_means(a), case_means(b)
    keys = sorted(ca.keys() & cb.keys(), key=str)
    return keys, np.array([ca[k] for k in keys]), np.array([cb[k] for k in keys])


def mcnemar_cases(
    a: Mapping[Hashable, float], b: Mapping[Hashable, float]
) -> tuple[int, int, int, float] | None:
    """(n cases, a-only correct, b-only correct, exact two-sided p) on per-case majorities."""
    keys, x, y = _paired(a, b)
    if not keys:
        return None
    return mcnemar(
        {k: float(v > 0.5) for k, v in zip(keys, x, strict=True)},
        {k: float(v > 0.5) for k, v in zip(keys, y, strict=True)},
    )


def sign_flip(
    a: Mapping[Hashable, float],
    b: Mapping[Hashable, float],
    *,
    shift: float = 0.0,
    alternative: str = "two-sided",
    n: int = BOOT_N,
    seed: int = BOOT_SEED,
) -> float | None:
    """p of the mean per-case difference d = a - b under random sign flips of d + `shift`
    (H0: Δ = -shift, differences symmetric). `alternative`: "two-sided", "greater" (Δ >
    -shift) or "less" (Δ < -shift). Exact when at most `EXACT_MAX` terms are non-zero, else
    Monte Carlo with (hits + 1) / (n + 1). Non-inferiority at margin m: shift=m, "greater"."""
    keys, x, y = _paired(a, b)
    if not keys:
        return None
    d = x - y + shift
    d = d[np.abs(d) > 1e-12]
    if not len(d):
        return 1.0
    t = d.sum()
    if len(d) <= EXACT_MAX:
        signs = ((np.arange(2 ** len(d))[:, None] >> np.arange(len(d))[None, :]) & 1) * 2 - 1
        null = signs @ d
    else:
        null = np.random.default_rng(seed).choice((-1.0, 1.0), size=(n, len(d))) @ d
    eps = 1e-9
    if alternative == "greater":
        hits = null >= t - eps
    elif alternative == "less":
        hits = null <= t + eps
    else:
        hits = np.abs(null) >= abs(t) - eps
    if len(d) <= EXACT_MAX:
        return float(np.mean(hits))
    return (int(hits.sum()) + 1) / (n + 1)


def paired_delta(
    a: Mapping[Hashable, float],
    b: Mapping[Hashable, float],
    *,
    level: float = 0.95,
    n: int = BOOT_N,
    seed: int = BOOT_SEED,
) -> tuple[float, float, float] | None:
    """(Δ, lo, hi): paired cluster-bootstrap percentile CI of mean(a) - mean(b) over the
    cases both scored (per-case means over reps; case ids resampled)."""
    keys, x, y = _paired(a, b)
    if not keys:
        return None
    d = x - y
    means = d[_resamples(len(keys), n, seed)].mean(axis=1)
    tail = 100 * (1 - level) / 2
    lo, hi = np.percentile(means, [tail, 100 - tail])
    return float(d.mean()), float(lo), float(hi)


def holm(pvalues: Mapping[str, float | None]) -> dict[str, float | None]:
    """Holm step-down adjusted p-values of ONE family (None stays None, not counted)."""
    items = sorted(((p, k) for k, p in pvalues.items() if p is not None), key=lambda t: t[0])
    m = len(items)
    out: dict[str, float | None] = dict.fromkeys(pvalues)
    running = 0.0
    for i, (p, k) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


def non_inferiority(
    a: Mapping[Hashable, float],
    b: Mapping[Hashable, float],
    margin: float,
    *,
    n: int = BOOT_N,
    seed: int = BOOT_SEED,
) -> dict[str, Any]:
    """a is non-inferior to b when the lower bound of the two-sided 95% paired CI of Δ (the
    one-sided 97.5% bound) is above -margin."""
    ci = paired_delta(a, b, level=0.95, n=n, seed=seed)
    if ci is None:
        return {"delta": None, "lo": None, "hi": None, "non_inferior": None}
    return {"delta": ci[0], "lo": ci[1], "hi": ci[2], "non_inferior": ci[1] > -margin}


def tost(
    a: Mapping[Hashable, float],
    b: Mapping[Hashable, float],
    margin: float,
    *,
    alpha: float = 0.05,
    n: int = BOOT_N,
    seed: int = BOOT_SEED,
) -> dict[str, Any]:
    """Two one-sided tests by the CI inclusion rule: the (1 - 2 alpha) paired CI of Δ inside
    (-margin, margin) -> "equivalent"; entirely outside -> "not equivalent"; else
    "inconclusive"."""
    ci = paired_delta(a, b, level=1 - 2 * alpha, n=n, seed=seed)
    if ci is None:
        return {"delta": None, "lo": None, "hi": None, "conclusion": None}
    point, lo, hi = ci
    if -margin < lo and hi < margin:
        conclusion = "equivalent"
    elif lo >= margin or hi <= -margin:
        conclusion = "not equivalent"
    else:
        conclusion = "inconclusive"
    return {"delta": point, "lo": lo, "hi": hi, "conclusion": conclusion}


KINDS = ("two_sided", "greater", "non_inferiority", "equivalence")


@dataclass(frozen=True)
class Contrast:
    """One pre-registered paired comparison `run - reference` on the headline score.
    `kind`: two_sided (Δ != 0), greater (Δ > 0, one-sided), non_inferiority (Δ > -margin),
    equivalence (TOST, |Δ| < margin). Holm adjusts the p-values within each `family`."""

    run: str
    reference: str
    family: str = "exploratory"
    kind: str = "two_sided"
    margin: float = 0.03

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"contrast kind {self.kind!r} not in {KINDS}")

    @classmethod
    def parse(cls, spec: str) -> Contrast:
        """`run:reference[:family[:kind[:margin]]]` (CLI form)."""
        parts = spec.split(":")
        if len(parts) < 2 or not all(parts[:2]):
            raise ValueError(f"bad contrast {spec!r}: run:reference[:family[:kind[:margin]]]")
        kw: dict[str, Any] = {"run": parts[0], "reference": parts[1]}
        if len(parts) > 2 and parts[2]:
            kw["family"] = parts[2]
        if len(parts) > 3 and parts[3]:
            kw["kind"] = parts[3]
        if len(parts) > 4 and parts[4]:
            kw["margin"] = float(parts[4])
        return cls(**kw)


def contrast_p(
    c: Contrast, a: Mapping[Hashable, float], b: Mapping[Hashable, float], **kw: Any
) -> float | None:
    """Case-level sign-flip p-value of the contrast's hypothesis."""
    if c.kind == "two_sided":
        return sign_flip(a, b, **kw)
    if c.kind == "greater":
        return sign_flip(a, b, alternative="greater", **kw)
    if c.kind == "non_inferiority":
        return sign_flip(a, b, shift=c.margin, alternative="greater", **kw)
    lo = sign_flip(a, b, shift=c.margin, alternative="greater", **kw)
    hi = sign_flip(a, b, shift=-c.margin, alternative="less", **kw)
    return None if lo is None or hi is None else max(lo, hi)


def evaluate_contrasts(
    scores: Mapping[str, Mapping[Hashable, float]],
    contrasts: Sequence[Contrast],
    *,
    alpha: float = 0.05,
    n: int = BOOT_N,
    seed: int = BOOT_SEED,
) -> list[dict[str, Any]]:
    """Per contrast: paired Δ 95% CI, case-level McNemar and sign-flip p, Holm-adjusted p
    within its family and the decision; margin kinds add the NI / TOST CI verdict. A run or
    reference missing from `scores` yields a row with `missing` set."""
    out: list[dict[str, Any]] = []
    for c in contrasts:
        row: dict[str, Any] = {"contrast": c}
        a, b = scores.get(c.run), scores.get(c.reference)
        if a is None or b is None:
            row["missing"] = c.run if a is None else c.reference
            out.append(row)
            continue
        row["n_cases"] = len(case_means(a).keys() & case_means(b).keys())
        row["delta_ci"] = paired_delta(a, b, n=n, seed=seed)
        row["mcnemar"] = mcnemar_cases(a, b)
        row["p"] = contrast_p(c, a, b, n=n, seed=seed)
        if c.kind == "non_inferiority":
            row["verdict"] = non_inferiority(a, b, c.margin, n=n, seed=seed)
        elif c.kind == "equivalence":
            row["verdict"] = tost(a, b, c.margin, alpha=alpha, n=n, seed=seed)
        out.append(row)
    families: dict[str, dict[str, float | None]] = {}
    for i, row in enumerate(out):
        if "missing" not in row:
            families.setdefault(row["contrast"].family, {})[str(i)] = row["p"]
    for fam in families.values():
        for k, adj in holm(fam).items():
            out[int(k)]["p_holm"] = adj
            out[int(k)]["reject"] = adj is not None and adj < alpha
    return out


def fmt_ci(ci: tuple[float, float, float] | None, *, scale: float = 100.0, digits: int = 1) -> str:
    if ci is None:
        return "-"
    p, lo, hi = (scale * x for x in ci)
    return f"{p:.{digits}f} [{lo:.{digits}f}, {hi:.{digits}f}]"
