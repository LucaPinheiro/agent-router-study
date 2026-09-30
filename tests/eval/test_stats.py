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


# ---------------------------------------------------------------- F4: case-level inference


def test_f4_case_means_average_the_reps_of_a_case() -> None:
    from routing_study.eval.stats import case_means

    got = case_means({("a", 1): 1.0, ("a", 2): 0.0, ("a", 3): 1.0, ("b", 1): 0.0})
    assert got == {"a": pytest.approx(2 / 3), "b": 0.0}
    assert case_means({"a": 1.0}) == {"a": 1.0}  # already case-keyed


def test_f4_mcnemar_is_case_level_not_rep_level() -> None:
    """3 reps of 10 discordant cases: rep-level McNemar sees 30 discordant pairs (too small a
    p-value); the case-level test sees 10."""
    from routing_study.eval.stats import mcnemar_cases

    a = {(f"c{i}", r): 1.0 for i in range(20) for r in (1, 2, 3)}
    b = {(f"c{i}", r): float(i < 10) for i in range(20) for r in (1, 2, 3)}
    n, a_only, b_only, p = mcnemar_cases(a, b)
    assert (n, a_only, b_only) == (20, 10, 0) and p == pytest.approx(2 / 2**10)
    assert mcnemar(a, b)[1] == 30  # the old rep-level count


def test_f4_sign_flip_permutation_exact_and_monte_carlo() -> None:
    from routing_study.eval.stats import sign_flip

    a = {f"c{i}": 1.0 for i in range(8)}
    b = {f"c{i}": 0.0 for i in range(8)}
    # exact: 2 of 2^8 sign patterns reach |mean| = 1
    assert sign_flip(a, b) == pytest.approx(2 / 2**8)
    assert sign_flip(a, a) == 1.0
    big_a = {f"c{i}": float(i % 3 != 0) for i in range(200)}
    big_b = {f"c{i}": float(i % 2 == 0) for i in range(200)}
    p = sign_flip(big_a, big_b, n=2000)
    assert 0 < p <= 1 and p == sign_flip(big_a, big_b, n=2000)  # seeded


def test_f4_paired_bootstrap_delta_resamples_cases_and_brackets_the_point() -> None:
    from routing_study.eval.stats import paired_delta

    a = {(f"c{i}", r): float(i < 15) for i in range(20) for r in (1, 2)}
    b = {(f"c{i}", r): float(i < 10) for i in range(20) for r in (1, 2)}
    point, lo, hi = paired_delta(a, b, n=2000)
    assert point == pytest.approx(0.25) and lo < 0.25 < hi and lo >= 0.0
    assert paired_delta(a, b, n=2000) == (point, lo, hi)  # seeded
    assert paired_delta(a, {}) is None
    # identical per-case differences: a zero-width interval
    same = paired_delta(a, a, n=500)
    assert same == (0.0, 0.0, 0.0)


def test_f4_holm_adjusts_within_a_family_step_down_and_monotone() -> None:
    from routing_study.eval.stats import holm

    adj = holm({"h1": 0.01, "h2": 0.04, "h3": 0.03})
    assert adj["h1"] == pytest.approx(0.03)
    assert adj["h3"] == pytest.approx(0.06)
    assert adj["h2"] == pytest.approx(0.06)  # monotone: never below the previous step
    assert holm({}) == {} and holm({"x": 0.9})["x"] == 0.9
    assert holm({"a": 0.5, "b": 0.6}) == {"a": 1.0, "b": 1.0}  # capped at 1


def test_f4_tost_equivalence_and_non_inferiority() -> None:
    from routing_study.eval.stats import non_inferiority, tost

    cases = [f"c{i}" for i in range(400)]
    a = {c: float(i % 10 != 0) for i, c in enumerate(cases)}  # 90%
    b = {c: float(i % 10 != 1) for i, c in enumerate(cases)}  # 90%, different cases
    eq = tost(a, b, margin=0.05, n=2000)
    assert eq["conclusion"] == "equivalent" and -0.05 < eq["lo"] <= eq["hi"] < 0.05
    worse = {c: float(i % 10 > 2) for i, c in enumerate(cases)}  # 70%
    ne = tost(worse, a, margin=0.03, n=2000)
    assert ne["conclusion"] == "not equivalent"
    ni = non_inferiority(a, b, margin=0.05, n=2000)
    assert ni["non_inferior"] and ni["lo"] > -0.05
    assert not non_inferiority(worse, a, margin=0.03, n=2000)["non_inferior"]


def test_f4_sign_flip_one_sided_with_a_margin_shift() -> None:
    from routing_study.eval.stats import sign_flip

    a = {f"c{i}": 1.0 for i in range(10)}
    # a is better everywhere: strongly non-inferior at any margin, never "less"
    assert sign_flip(a, {k: 0.0 for k in a}, shift=0.03, alternative="greater") < 0.01
    assert sign_flip(a, {k: 0.0 for k in a}, alternative="less") == 1.0


def test_f4_contrasts_are_holm_adjusted_within_families_with_a_configurable_reference() -> None:
    from routing_study.eval.stats import Contrast, evaluate_contrasts

    cases = [f"c{i}" for i in range(60)]
    ref = {(c, 1): float(i < 45) for i, c in enumerate(cases)}  # 75%
    better = {(c, 1): float(i < 57) for i, c in enumerate(cases)}  # 95%
    same = dict(ref)
    contrasts = [
        Contrast("better", "ref", family="H", kind="two_sided"),
        Contrast("same", "ref", family="H", kind="two_sided"),
        Contrast("better", "same", family="S", kind="non_inferiority", margin=0.03),
        Contrast("ghost", "ref"),
    ]
    rows = evaluate_contrasts({"ref": ref, "better": better, "same": same}, contrasts, n=2000)
    h1, h2, ni, ghost = rows
    assert h1["n_cases"] == 60 and h1["delta_ci"][0] == pytest.approx(0.2)
    assert h1["mcnemar"][1:3] == (12, 0) and h1["reject"]
    assert h2["p"] == 1.0 and not h2["reject"]
    assert h1["p_holm"] == pytest.approx(min(1.0, 2 * h1["p"]))  # 2 tests in family H
    assert ni["p_holm"] == ni["p"] and ni["verdict"]["non_inferior"]  # alone in family S
    assert ghost["missing"] == "ghost"
    assert Contrast.parse("e9:e5_tuned:H1:non_inferiority:0.03") == Contrast(
        "e9", "e5_tuned", "H1", "non_inferiority", 0.03
    )
    with pytest.raises(ValueError):
        Contrast.parse("only-one")
    with pytest.raises(ValueError):
        Contrast("a", "b", kind="bogus")
