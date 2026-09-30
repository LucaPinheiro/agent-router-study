"""eval/metrics.py: recall@k, abstention P/R, risk-coverage, calibration, baselines (F6)."""

from __future__ import annotations

import pytest

from routing_study.eval import metrics as m

EXP = {"acceptable_skills": ["pedidos"], "acceptable_tools": ["track"], "args": {}}
OOS = {"acceptable_skills": ["__abstain__"], "acceptable_tools": ["__abstain__"], "args": {}}


def _row(tool, cands=(), skill_ok=1.0, exp=EXP, **kw):
    return {
        "mode": "routing-only",
        "native": False,
        "error": kw.get("error"),
        "expected": exp,
        "skill": {"choice": kw.get("skill", "pedidos"), "confidence": kw.get("sc", 0.9)},
        "tool": {"choice": tool, "confidence": kw.get("tc", 0.8), "candidates": list(cands)},
        "scores": {"skill_correct": skill_ok, "tool_correct": float(tool == "track")},
    }


def test_recall_at_k_uses_the_ranked_candidates_and_needs_the_right_skill():
    r = _row("cancel", [["cancel", 0.6], ["track", 0.3], ["x", 0.1]])
    assert [m.recall_at_k(r, k) for k in (1, 2, 3)] == [0.0, 1.0, 1.0]
    assert m.recall_at_k(_row("track", skill_ok=0.0), 3) == 0.0
    assert m.recall_at_k(_row("track", error="boom"), 3) == 0.0
    esc = _row("escalate_to_human", exp=OOS)
    assert m.recall_at_k(esc, 1) == 1.0


def test_abstention_precision_and_recall():
    rows = [
        _row("escalate_to_human", exp=OOS),  # TP
        _row("track", exp=OOS),  # FN
        _row("escalate_to_human"),  # FP (gold does not allow abstaining)
        _row("track"),
    ]
    pr = m.abstention_pr(rows)
    assert pr["n_abstained"] == 2 and pr["n_expected"] == 2
    assert pr["precision"] == 0.5 and pr["recall"] == 0.5


def test_risk_coverage_aurc_and_coverage_at_risk():
    pairs = [(0.9, 1), (0.8, 1), (0.7, 0), (0.6, 1)]
    rc = m.risk_coverage(pairs, target=0.05)
    assert rc["coverage"] == [0.25, 0.5, 0.75, 1.0]
    assert rc["risk"] == pytest.approx([0, 0, 1 / 3, 1 / 4])
    assert rc["aurc"] == pytest.approx((0 + 0 + 1 / 3 + 1 / 4) / 4)
    assert rc["coverage_at_risk"] == 0.5
    tied = m.risk_coverage([(0.5, 1), (0.5, 0)])
    assert tied["coverage"] == [1.0] and tied["aurc"] == 0.5
    assert m.risk_coverage([]) is None


def test_calibration_brier_and_adaptive_ece_with_bin_counts():
    pairs = [(0.9, 1)] * 9 + [(0.9, 0)] + [(0.2, 0)] * 10
    c = m.calibration(pairs, bins=2)
    assert [b[0] for b in c["bins"]] == [10, 10]  # equal-mass bins
    assert c["ece"] == pytest.approx(0.5 * 0.2 + 0.5 * 0.0)
    assert c["brier"] == pytest.approx((9 * 0.01 + 0.81 + 10 * 0.04) / 20)


def test_level_pairs_skip_abstentions_errors_and_wrong_skill_tools():
    rows = [_row("track"), _row("track", skill_ok=0.0), _row(None), _row("x", error="e")]
    assert m.level_pairs(rows, "skill") == [(0.9, 1.0), (0.9, 0.0), (0.9, 1.0)]
    assert m.level_pairs(rows, "tool") == [(0.8, 1.0)]


def test_trivial_baselines():
    skill_tools = {"pedidos": ["track", "cancel"], "__global__": ["escalate_to_human"]}
    dev = [{"expected": EXP}] * 3 + [{"expected": OOS}]
    cases = [{"expected": EXP}, {"expected": OOS}]
    b = m.baselines(cases, dev, skill_tools)
    assert b["always_escalate"]["joint_correct"] == 0.5  # only the out-of-scope case
    assert b["majority"]["joint_correct"] == 0.5  # pedidos/track
    # uniform: skills {pedidos, __global__}; EXP right only via pedidos/track (1/2 * 1/3);
    # OOS right only via __global__/escalate (1/2 * 1/1)
    assert b["uniform"]["joint_correct"] == pytest.approx((1 / 6 + 1 / 2) / 2)
    assert m.skill_tools_of(
        [{"name": "t", "_meta": {"br.routingstudy/skill": "s"}}, {"name": "g"}]
    ) == {"s": ["t"], "__global__": ["g"]}
