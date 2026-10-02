"""scripts/analysis/phase2_b.py: H1-L (e2e_success_sym E9-L − E0-L) on synthetic rows."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "analysis"))

import phase2_b  # noqa: E402


def _row(case: str, success: float, cost: float, *, error: str | None = None) -> dict:
    return {
        "case_id": case,
        "rep": 1,
        "mode": "e2e",
        "error": error,
        "scores": {"e2e_success": success},
        "cost_usd": {"total": cost},
    }


def _arms(n: int = 40) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """E9 wins on cases 0-5 (sym), E0 wins on 6-7; the legacy scorer takes 3 E9 wins away."""
    e9_sym, e0_sym, e9_leg, e0_leg = [], [], [], []
    for i in range(n):
        c = f"c{i:02d}"
        e9 = 1.0 if i < 6 or 8 <= i < 20 else 0.0
        e0 = 1.0 if 6 <= i < 20 else 0.0
        e9_sym.append(_row(c, e9, 0.02))
        e0_sym.append(_row(c, e0, 0.01))
        e9_leg.append(_row(c, 0.0 if i < 3 else e9, 0.02))
        e0_leg.append(_row(c, e0, 0.01))
    return e9_sym, e0_sym, e9_leg, e0_leg


def test_h1l_delta_ci_cost_and_verdict_changes() -> None:
    e9_sym, e0_sym, e9_leg, e0_leg = _arms()
    out = phase2_b.h1l(e9_sym, e0_sym, e9_leg, e0_leg)
    sym, leg = out["sym"], out["legacy"]
    # Δ = (18 − 14) / 40 = +10 pp sym; (15 − 14) / 40 = +2.5 pp legacy
    assert sym["delta_ci"][0] == pytest.approx(0.10)
    assert leg["delta_ci"][0] == pytest.approx(0.025)
    lo, hi = sym["delta_ci"][1:]
    assert lo <= 0.10 <= hi
    assert sym["n_cases"] == 40
    assert sym["mcnemar"][1:3] == (6, 2)
    # deterministic (seeded) bootstrap
    assert phase2_b.h1l(e9_sym, e0_sym, e9_leg, e0_leg)["sym"]["delta_ci"] == sym["delta_ci"]
    ratio = out["cost_ratio"]
    assert ratio[0] == pytest.approx(2.0) and ratio[3] == 40
    assert out["verdict_changes"]["E9"] == {"turns": 40, "fail_to_success": 3, "success_to_fail": 0}
    assert out["verdict_changes"]["E0"]["fail_to_success"] == 0
    assert out["pair_outcome_changes"] == 3


def test_h1l_itt_error_row_counts_as_failure() -> None:
    e9_sym, e0_sym, e9_leg, e0_leg = _arms()
    e9_sym[0] = _row("c00", 1.0, 0.02, error="timeout")
    out = phase2_b.h1l(e9_sym, e0_sym, e9_leg, e0_leg)
    assert out["sym"]["delta_ci"][0] == pytest.approx(0.075)


def test_primary_family_holm_counts_not_run_hypotheses() -> None:
    e9_sym, e0_sym, _, _ = _arms()
    scores = phase2_b.primary_scores({}, {"E9": e9_sym, "E0": e0_sym})
    res = phase2_b.evaluate_family(scores, phase2_b.PRIMARY)
    h1, h2, h3 = res
    assert "missing" in h2 and "missing" in h3
    # H2-L / H3-L not run enter Holm with p = 1: H1-L is adjusted with m = 3
    assert h1["p_holm"] == pytest.approx(min(1.0, 3 * h1["p"]))
    assert h2["reject"] is False and h3["reject"] is False


def test_same_calls_and_orig_subset() -> None:
    a = [
        {"case_id": "x", "rep": 1, "calls": [{"name": "cancel_order", "status": "completed"}]},
        {"case_id": "y", "rep": 1, "calls": []},
    ]
    b = [
        {
            "case_id": "x",
            "rep": 1,
            "calls": [{"name": "load_skill"}, {"name": "cancel_order", "status": "completed"}],
        },
        {"case_id": "y", "rep": 1, "calls": [{"name": "get_order_status", "status": "completed"}]},
    ]
    assert phase2_b.same_calls_cases(a, b) == {"x"}
    assert phase2_b.orig_case(
        {"category": "direto", "expected": {"acceptable_tools": ["cancel_order"]}}
    )
    assert not phase2_b.orig_case(
        {"category": "direto", "expected": {"acceptable_tools": ["cancel_subscription"]}}
    )
    assert phase2_b.orig_case(
        {"category": "fora_escopo", "expected": {"acceptable_tools": ["__abstain__"]}}
    )
