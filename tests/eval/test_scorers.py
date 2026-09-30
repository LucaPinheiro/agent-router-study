"""Scorers, grounding, offline cascade simulation and the report table."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from routing_study.eval.grounding import answer_facts, grounded
from routing_study.eval.report import render, summarize
from routing_study.eval.runner import load_cases
from routing_study.eval.scorers import chosen_skill, score_turn
from routing_study.eval.simulate import simulate
from routing_study.settings import PipelineStep, RoutingConfig, Settings, StageConfig

SCHEMAS = {"cancel_order": {"type": "object", "additionalProperties": False,
                            "properties": {"order_id": {"type": ["string", "null"]}}}}
PROFILE = {"status": "completed", "orders": [{"order_id": "O0001", "created_at": "2026-09-29",
                                              "total": {"amount": 1299.9}}]}


def _rec(calls: list[dict[str, Any]], *, native: bool = False, answer: str | None = "ok",
         skill: str | None = "pedidos_logistica", outcome: str = "answered") -> dict[str, Any]:
    return {"native": native, "mode": "e2e", "calls": calls, "outcome": outcome,
            "final_answer": answer, "customer": PROFILE,
            "skill": {"choice": skill, "abstained": skill is None, "resolved_by": "regex"},
            "tool": None}


def _call(name: str, args: dict[str, Any] | None = None, status: str = "completed",
          structured: dict[str, Any] | None = None, skill: str = "pedidos_logistica"
          ) -> dict[str, Any]:
    return {"name": name, "args": args or {}, "skill": skill, "status": status,
            "structured": structured or {"status": status}}


EXPECTED = {"acceptable_skills": ["pedidos_logistica"], "acceptable_tools": ["cancel_order"],
            "args": {"order_id": "O0001"}}


def test_grounding_accepts_facts_present_in_structured_content() -> None:
    structured = [PROFILE, {"protocol": "CAN-1A2B3C4D", "refund_by": "2026-10-09",
                            "tracking_code": "BR6B8CC1D87BR"}]
    ok, missing = grounded("Pedido O0001 (R$ 1.299,90) cancelado: protocolo CAN-1A2B3C4D, "
                           "estorno até 09/10/2026 ou 2026-10-09, rastreio BR6B8CC1D87BR.",
                           structured)
    assert ok, missing


def test_grounding_flags_invented_ids_amounts_and_dates() -> None:
    ok, missing = grounded("Protocolo CAN-FFFFFFFF, valor R$ 10,00, prazo 01/12.", [PROFILE])
    assert not ok
    assert missing == ["date_md:12-01", "id:CAN-FFFFFFFF", "money:10.0"]
    assert answer_facts("sem fatos verificáveis") == set()


def test_score_turn_success_and_arg_mismatch() -> None:
    good = _rec([_call("cancel_order", {"order_id": "o0001"})])
    assert score_turn(good, EXPECTED, SCHEMAS)["e2e_success"] == 1.0
    wrong = score_turn(_rec([_call("cancel_order", {"order_id": "O0002"}, status="error")]),
                       EXPECTED, SCHEMAS)
    assert wrong["tool_correct"] == 1.0 and wrong["args_valid"] == 0.0
    assert wrong["e2e_success"] == 0.0
    bad_schema = score_turn(_rec([_call("cancel_order", {"order_id": "O0001", "x": 1})]),
                            EXPECTED, SCHEMAS)
    assert bad_schema["args_valid"] == 0.0


CLARIFY = {"status": "error", "code": "VALIDATION_ERROR", "recoverable": True,
           "message": "O cliente tem 3 pedidos; informe order_id.",
           "details": {"options": ["O0001", "O0002", "O0003"]}}
NO_ORDER = {**EXPECTED, "args": {}}


def test_clarification_counts_as_e2e_success() -> None:
    asked = _rec([_call("cancel_order", status="error", structured=CLARIFY)],
                 answer="Qual pedido você quer cancelar: O0001, O0002 ou O0003?")
    assert score_turn(asked, NO_ORDER, SCHEMAS)["e2e_success"] == 1.0
    completed = _rec([_call("cancel_order", {"order_id": "O0002"})])
    assert score_turn(completed, NO_ORDER, SCHEMAS)["e2e_success"] == 1.0


def test_clarification_requires_offering_the_options() -> None:
    silent = _rec([_call("cancel_order", status="error", structured=CLARIFY)],
                  answer="Não consegui cancelar agora, tente mais tarde.")
    assert score_turn(silent, NO_ORDER, SCHEMAS)["e2e_success"] == 0.0
    # the user named the order: a validation error is a failure, not a clarification
    named = _rec([_call("cancel_order", status="error", structured=CLARIFY)],
                 answer="Qual pedido: O0001, O0002 ou O0003?")
    assert score_turn(named, EXPECTED, SCHEMAS)["e2e_success"] == 0.0
    not_found = {**CLARIFY, "code": "NOT_FOUND"}
    wrong_code = _rec([_call("cancel_order", status="error", structured=not_found)],
                      answer="Qual pedido: O0001, O0002 ou O0003?")
    assert score_turn(wrong_code, NO_ORDER, SCHEMAS)["e2e_success"] == 0.0


def test_escalation_counts_as_abstention() -> None:
    exp = {"acceptable_skills": ["__abstain__", "__global__"],
           "acceptable_tools": ["__abstain__", "escalate_to_human"], "args": {}}
    rec = _rec([_call("escalate_to_human", skill="__global__")], native=True)
    s = score_turn(rec, exp, {"escalate_to_human": {"type": "object"}})
    assert chosen_skill(rec) == "__global__"
    assert s["abstain_correct"] == s["skill_correct"] == s["e2e_success"] == 1.0
    # acting on an out-of-scope request is the failure abstain_correct catches
    acted = score_turn(_rec([_call("cancel_order")]), exp, SCHEMAS)
    assert acted["abstain_correct"] == 0.0


def test_native_skill_is_the_first_loaded_skill() -> None:
    rec = _rec([_call("load_skill", {"skill": "trocas_devolucoes"}), _call("cancel_order")],
               native=True)
    assert chosen_skill(rec) == "trocas_devolucoes"
    assert chosen_skill(_rec([], native=True)) == "__abstain__"


def _shadow(choice: str | None, conf: float, strategy: str, cost: float = 0.0) -> dict[str, Any]:
    return {"choice": choice, "confidence": conf, "candidates": [], "strategy": strategy,
            "latency_ms": 10.0, "cost_usd": cost, "usage": {}, "cached": False}


def _result_row(case: str, regex: tuple[str | None, float], llm: str, *, rep: int = 1,
                error: str | None = None) -> dict[str, Any]:
    skill_shadow = {"regex": _shadow(*regex, "regex"), "llm": _shadow(llm, 0.9, "llm", 0.001)}
    return {
        "run_name": "e9-shadow", "config": "e9", "mode": "routing-only", "case_id": case,
        "rep": rep, "error": error,
        "expected": {"acceptable_skills": ["pedidos_logistica"],
                     "acceptable_tools": ["get_order_status"]},
        "skill": {"choice": llm, "shadow": skill_shadow},
        "tool": {"choice": "get_order_status",
                 "shadow": {"regex": _shadow("get_order_status", 0.95, "regex"),
                            "llm": _shadow("track_shipment", 0.9, "llm", 0.002)}},
        "scores": {"skill_correct": 1.0, "tool_correct": 1.0, "resolved_by": "llm"},
        "cost_usd": {"routing": 0.003, "agent": 0.0, "total": 0.003},
        "latency_ms": {"turn": 100.0, "routing": 20.0},
    }


def test_simulate_replays_cascade_thresholds(tmp_path: Path) -> None:
    path = tmp_path / "shadow.jsonl"
    rows = [_result_row("a", ("pedidos_logistica", 0.95), "pedidos_logistica"),
            _result_row("b", ("pagamentos_reembolsos", 0.5), "pedidos_logistica")]
    path.write_text("\n".join(json.dumps(r) for r in rows))
    stage = StageConfig(pipeline=[PipelineStep(strategy="regex", min_confidence=0.9),
                                  PipelineStep(strategy="llm")])
    settings = Settings(_env_file=None, experiment_id="sim",
                        routing=RoutingConfig(mode="cascade", skill=stage, tool=stage))
    out = simulate(path, settings)
    assert out["skill_acc"] == 1.0  # b: regex below threshold -> llm decides correctly
    assert out["resolved_by"] == {"regex": 1, "llm": 1}
    assert out["tool_acc"] == 1.0 and out["tool_n"] == 2  # regex 0.95 decides the tool
    assert abs(out["routing_cost_case"] - 0.0005) < 1e-9  # only b paid the llm skill step


def test_report_summarizes_per_run(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    rows = [_result_row("a", ("x", 1.0), "y"), _result_row("b", ("x", 1.0), "y", error="boom")]
    path.write_text("\n".join(json.dumps(r) for r in rows))
    [row] = summarize([json.loads(x) for x in path.read_text().splitlines()])
    assert row["n"] == 2 and row["errors"] == 1 and row["skill_correct"] == [1.0]
    assert "e9-shadow" in render([path])


def test_load_cases_interleaves_categories(tmp_path: Path) -> None:
    rows = [{"id": f"{c}{i}", "category": c, "customer_id": "C001",
             "turns": [{"role": "user", "content": "x"}],
             "expected": {"acceptable_skills": ["__global__"], "acceptable_tools": ["x"]}}
            for c in ("a", "b") for i in range(3)]
    (tmp_path / "dataset_dev.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    assert [c.id for c in load_cases("dev", 4, data_dir=tmp_path)] == ["a0", "b0", "a1", "b1"]


def test_e2e_counts_business_refusal_as_executed() -> None:
    call = _call("cancel_order", {"order_id": "O0001"}, status="error")
    call["structured"] = {"status": "error", "code": "NOT_ELIGIBLE", "recoverable": False}
    exp = {"acceptable_skills": ["pedidos_logistica"], "acceptable_tools": ["cancel_order"],
           "args": {"order_id": "O0001"}}
    assert score_turn(_rec([call]), exp, SCHEMAS)["e2e_success"] == 1.0
