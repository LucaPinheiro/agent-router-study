"""simulate / report fixes: review H1, H2, M4, L1, L4 and code finding 9."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from routing_study.eval.report import render, summarize
from routing_study.eval.simulate import aggregate, simulate_rows
from routing_study.settings import PipelineStep, RoutingConfig, Settings, StageConfig

SKILLS = {"acceptable_skills": ["pedidos_logistica"], "acceptable_tools": ["get_order_status"]}
OOS = {"acceptable_skills": ["__abstain__"], "acceptable_tools": ["__abstain__"]}


def _d(strategy: str, choice: str | None, conf: float = 0.9, **usage: Any) -> dict[str, Any]:
    return {
        "choice": choice,
        "confidence": conf,
        "candidates": [],
        "strategy": strategy,
        "latency_ms": 10.0,
        "cost_usd": 0.001,
        "usage": usage,
        "cached": False,
    }


def _shadow_row(case: str, skill: dict, tool: dict | None, recorded: str | None, exp: dict):
    return {
        "case_id": case,
        "rep": 1,
        "category": "direto",
        "expected": exp,
        "error": None,
        "skill": {"choice": recorded, "shadow": skill},
        "tool": {"choice": None, "shadow": tool} if tool else None,
    }


def _single(strategy: str) -> Settings:
    stage = StageConfig(pipeline=[PipelineStep(strategy=strategy)])
    return Settings(
        _env_file=None,
        experiment_id=strategy,
        routing=RoutingConfig(mode="single", skill=stage, tool=stage),
    )


def test_h2_wrong_simulated_skill_scores_zero_instead_of_being_dropped() -> None:
    rows = [
        # recorded (llm) routed right; embedding picked a wrong skill
        _shadow_row(
            "a",
            {"llm": _d("llm", "pedidos_logistica"), "embedding": _d("embedding", "pagamentos")},
            {
                "llm": _d("llm", "get_order_status"),
                "embedding": _d("embedding", "get_order_status"),
            },
            "pedidos_logistica",
            SKILLS,
        ),
        _shadow_row(
            "b",
            {
                "llm": _d("llm", "pedidos_logistica"),
                "embedding": _d("embedding", "pedidos_logistica"),
            },
            {
                "llm": _d("llm", "get_order_status"),
                "embedding": _d("embedding", "get_order_status"),
            },
            "pedidos_logistica",
            SKILLS,
        ),
    ]
    emb = aggregate(simulate_rows(rows, _single("embedding")))
    assert emb["n"] == 2 and emb["tool_unavailable"] == 0
    assert emb["skill_acc"] == 0.5 and emb["joint_acc"] == 0.5  # not 100% on 1 kept row


def test_h1_simulated_global_escalation_is_credited_like_score_turn() -> None:
    row = _shadow_row(
        "a",
        {"jev": _d("jev", "__global__"), "regex": _d("regex", None, 0.0)},
        {"jev": _d("jev", "escalate_to_human")},
        "__global__",
        OOS,
    )
    for strategy in ("jev", "regex"):
        [res] = simulate_rows([row], _single(strategy))
        assert res["skill_correct"] == res["joint_correct"] == 1.0, strategy


def test_m4_shadow_error_or_parse_fail_is_an_error_not_an_abstention() -> None:
    row = _shadow_row(
        "a",
        {"jev": _d("jev", None, 0.0, parse_fail=True), "llm": _d("llm", None, 0.0, error="x")},
        None,
        None,
        OOS,
    )
    for strategy in ("jev", "llm"):
        [res] = simulate_rows([row], _single(strategy))
        assert res["error"], strategy
    agg = aggregate(simulate_rows([row], _single("jev")))
    # F2 (ITT): the error row stays in the denominator and counts as wrong
    assert (agg["n"], agg["errors"], agg["n_ok"]) == (1, 1, 0)
    assert agg["joint_acc"] == agg["skill_acc"] == 0.0 and agg["error_rate"] == 1.0
    assert agg["joint_acc_error_free"] is None


def test_f2_simulate_itt_counts_error_rows_as_wrong_and_keeps_error_free_sensitivity() -> None:
    ok = _shadow_row(
        "a",
        {"llm": _d("llm", "pedidos_logistica")},
        {"llm": _d("llm", "get_order_status")},
        "pedidos_logistica",
        SKILLS,
    )
    bad = _shadow_row("b", {"llm": _d("llm", None, 0.0, error="Timeout")}, None, None, OOS)
    agg = aggregate(simulate_rows([ok, bad], _single("llm")))
    assert agg["n"] == 2 and agg["errors"] == 1 and agg["error_rate"] == 0.5
    assert agg["joint_acc"] == 0.5 and agg["joint_acc_error_free"] == 1.0


def _rescored(run: str, config: str, case: str, joint: float, error: str | None = None) -> dict:
    return {
        "run_name": run,
        "config": config,
        "mode": "routing-only",
        "case_id": case,
        "rep": 1,
        "error": error,
        "calls": [],
        "scores": {"skill_correct": 1.0, "tool_correct": joint, "joint_correct": joint},
        "cost_usd": {"total": 0.001, "billed_total": 0.0},
        "latency_ms": {"turn": 1.0, "routing": 5.0, "executor": None},
    }


def test_f2_report_is_itt_with_error_rate_and_an_error_free_sensitivity(tmp_path: Path) -> None:
    rows = []
    for i in range(20):
        rows.append(_rescored("e5", "e5_llm_sonnet", f"c{i}", 1.0))
        rows.append(_rescored("e3", "e3_embedding", f"c{i}", float(i < 10)))
    # the scores of an error row are ignored: it is wrong whatever they say (ITT)
    rows.append(_rescored("e3", "e3_embedding", "c20", 1.0, error="timeout"))
    rows.append(_rescored("e5", "e5_llm_sonnet", "c20", 1.0))
    by = {r["run"]: r for r in summarize(rows)}
    assert by["e3"]["n"] == 21 and by["e3"]["errors"] == 1
    assert by["e3"]["error_rate"] == pytest.approx(1 / 21)
    assert by["e3"]["joint_correct"] == [1.0] * 10 + [0.0] * 11
    assert by["e3"]["headline_ci"][0] == pytest.approx(10 / 21)
    # sensitivity: c20 dropped for both runs
    assert by["e5"]["n_shared"] == by["e3"]["n_shared"] == 20
    assert by["e3"]["error_free_ci"][0] == pytest.approx(0.5)
    path = tmp_path / "r.jsonl"
    path.write_text(json.dumps({"_provenance": {}}) + "\n" + "\n".join(map(json.dumps, rows)))
    text = render([path])
    assert "tool_top1%" in text and "tool_first_call%" not in text  # L1 labels
    assert "intention to treat" in text and "err%" in text
    assert "SENSITIVITY: 20 case ids error-free in every run" in text


def test_f4_report_contrasts_use_a_configurable_reference_at_case_level(tmp_path: Path) -> None:
    from routing_study.eval.stats import Contrast

    rows = []
    for i in range(20):
        for rep in (1, 2, 3):
            rows.append(_rescored("e5", "e5_llm_sonnet_tuned", f"c{i}", 1.0) | {"rep": rep})
            rows.append(_rescored("e9", "e9_regex_jev_llm", f"c{i}", float(i < 10)) | {"rep": rep})
    path = tmp_path / "r.jsonl"
    path.write_text(json.dumps({"_provenance": {}}) + "\n" + "\n".join(map(json.dumps, rows)))
    text = render([path], reference="e5_llm_sonnet_tuned")
    # case level: 10 discordant CASES (not 30 (case, rep) pairs)
    assert "| vs e5_llm_sonnet_tuned | e9 | e5_llm_sonnet_tuned | two_sided | 20 " in text
    assert "0/10 p=0.00195" in text
    ni = Contrast("e9", "e5", family="H1", kind="non_inferiority", margin=0.03)
    text = render([path], contrasts=[ni])
    assert "| H1 | e9 | e5 | non_inferiority ±3pp | 20 | -50.0 [" in text
    assert "not shown" in text
    assert "contrasts" not in render([path])  # no implicit reference
