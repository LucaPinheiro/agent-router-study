"""Bootstrap and McNemar helpers (review L4)."""

from __future__ import annotations

import numpy as np
import pytest

from routing_study.eval.stats import bootstrap_mean, bootstrap_stat, fmt_ci, mcnemar


def test_l4_bootstrap_is_deterministic_and_brackets_the_point() -> None:
    groups = {f"c{i}": [float(i % 3 == 0)] * 3 for i in range(60)}
    a = bootstrap_mean(groups, n=2000)
    assert a == bootstrap_mean(groups, n=2000)  # fixed seed
    assert a is not None
    point, lo, hi = a
    assert point == pytest.approx(20 / 60) and lo < point < hi
    assert bootstrap_mean({}) is None


def test_l4_bootstrap_is_paired_across_configs_on_the_same_cases() -> None:
    """Same case ids -> same resamples: a config that is uniformly 1 point better has an
    interval shifted by exactly that amount."""
    base = {f"c{i}": [float(i % 2)] for i in range(40)}
    better = {k: [v[0] + 0.5] for k, v in base.items()}
    a, b = bootstrap_mean(base, n=500), bootstrap_mean(better, n=500)
    assert a is not None and b is not None
    assert b[1] - a[1] == pytest.approx(0.5) and b[2] - a[2] == pytest.approx(0.5)


def test_l4_bootstrap_median_latency() -> None:
    groups = {f"c{i}": [float(i)] for i in range(101)}
    ci = bootstrap_stat(groups, np.median, n=500)
    assert ci is not None and ci[0] == 50.0 and ci[1] <= 50.0 <= ci[2]


def test_l4_mcnemar_exact() -> None:
    a = {i: 1.0 for i in range(20)}
    b = {i: 1.0 if i < 10 else 0.0 for i in range(20)}
    n, a_only, b_only, p = mcnemar(a, b) or (0, 0, 0, 0.0)
    assert (n, a_only, b_only) == (20, 10, 0)
    assert p == pytest.approx(2 / 2**10)
    assert mcnemar(a, a) == (20, 0, 0, 1.0)
    assert mcnemar(a, {"x": 1.0}) is None
    assert fmt_ci((0.5, 0.4, 0.6)) == "50.0 [40.0, 60.0]" and fmt_ci(None) == "-"
