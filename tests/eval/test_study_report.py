"""scripts/analysis/study_report.py: ITT, error-free sensitivity (F2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "analysis"))

import study_report  # noqa: E402


def _x(case: str, joint: float, error: str | None = None) -> dict:
    return {
        "key": (case, 1),
        "case_id": case,
        "category": "direto",
        "error": error,
        "skill_correct": joint,
        "joint_correct": joint,
        "tool_unavailable": False,
        "confidence": 0.9,
        "resolved_by": "llm",
        "cost_usd": 0.001,
        "latency_ms": 10.0,
    }


def test_f2_entry_stats_counts_errors_as_wrong_and_reports_the_error_free_sensitivity():
    res = [_x(f"c{i}", 1.0) for i in range(3)] + [_x("c3", 1.0, error="llm: Timeout")]
    # an error row's leftover scores are ignored: it is wrong
    res[-1].pop("skill_correct")
    keys = {x["key"] for x in res}
    error_free = keys - {("c3", 1)}
    s = study_report.entry_stats("e", res, keys, error_free, error_free)
    assert s["n"] == 4 and s["errors"] == 1 and s["err_pct"] == "25.0"
    assert s["joint_ci"][0] == pytest.approx(0.75) and s["skill"] == "75.0"
    assert s["joint_ef_ci"][0] == 1.0


def test_f2_single_run_rows_zero_the_scores_of_an_error_row():
    row = {
        "case_id": "c",
        "rep": 1,
        "error": "llm: parse_fail",
        "scores": {"skill_correct": 1.0, "joint_correct": 1.0},
        "skill": {"confidence": 0.9},
        "cost_usd": {"routing": 0.0},
        "latency_ms": {"routing": 1.0},
    }
    [x] = study_report.single_run_rows([row])
    assert x["skill_correct"] == x["joint_correct"] == 0.0 and x["error"]
