"""simulate / report fixes: review H1, H2, M4, L1, L4 and code finding 9."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    assert aggregate(simulate_rows([row], _single("jev")))["n"] == 0


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


def test_m4_l4_report_compares_runs_on_shared_error_free_cases(tmp_path: Path) -> None:
    rows = []
    for i in range(20):
        rows.append(_rescored("e5", "e5_llm_sonnet", f"c{i}", 1.0))
        rows.append(_rescored("e3", "e3_embedding", f"c{i}", float(i < 10)))
    rows.append(_rescored("e3", "e3_embedding", "c20", 1.0, error="timeout"))
    rows.append(_rescored("e5", "e5_llm_sonnet", "c20", 1.0))
    by = {r["run"]: r for r in summarize(rows)}
    assert by["e5"]["n_shared"] == by["e3"]["n_shared"] == 20  # c20 dropped for both
    assert by["e3"]["joint_correct"] == [1.0] * 10 + [0.0] * 10
    assert by["e3"]["mcnemar"][:3] == (20, 0, 10) and by["e3"]["mcnemar"][3] < 0.01
    assert by["e3"]["headline_ci"][1] < 0.5 < by["e3"]["headline_ci"][2]
    path = tmp_path / "r.jsonl"
    path.write_text(json.dumps({"_provenance": {}}) + "\n" + "\n".join(map(json.dumps, rows)))
    text = render([path])
    assert "tool_top1%" in text and "tool_first_call%" not in text  # L1 labels
    assert "20 case ids error-free in every run" in text
