"""Scorers, grounding, offline cascade simulation and the report table."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from routing_study.eval.grounding import answer_facts, grounded
from routing_study.eval.report import render, summarize
from routing_study.eval.runner import load_cases
from routing_study.eval.scorers import chosen_skill, score_turn
from routing_study.eval.simulate import render_simulation, simulate
from routing_study.settings import PipelineStep, RoutingConfig, Settings, StageConfig

SCHEMAS = {
    "cancel_order": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"order_id": {"type": ["string", "null"]}},
    }
}
PROFILE = {
    "status": "completed",
    "orders": [{"order_id": "O0001", "created_at": "2026-09-29", "total": {"amount": 1299.9}}],
}


def _rec(
    calls: list[dict[str, Any]],
    *,
    native: bool = False,
    answer: str | None = "ok",
    skill: str | None = "pedidos_logistica",
    outcome: str = "answered",
) -> dict[str, Any]:
    return {
        "native": native,
        "mode": "e2e",
        "calls": calls,
        "outcome": outcome,
        "final_answer": answer,
        "customer": PROFILE,
        "skill": {"choice": skill, "abstained": skill is None, "resolved_by": "regex"},
        "tool": None,
    }


def _call(
    name: str,
    args: dict[str, Any] | None = None,
    status: str = "completed",
    structured: dict[str, Any] | None = None,
    skill: str = "pedidos_logistica",
) -> dict[str, Any]:
    return {
        "name": name,
        "args": args or {},
        "skill": skill,
        "status": status,
        "structured": structured or {"status": status},
    }


EXPECTED = {
    "acceptable_skills": ["pedidos_logistica"],
    "acceptable_tools": ["cancel_order"],
    "args": {"order_id": "O0001"},
}


def test_grounding_accepts_facts_present_in_structured_content() -> None:
    structured = [
        PROFILE,
        {"protocol": "CAN-1A2B3C4D", "refund_by": "2026-10-09", "tracking_code": "BR6B8CC1D87BR"},
    ]
    ok, missing = grounded(
        "Pedido O0001 (R$ 1.299,90) cancelado: protocolo CAN-1A2B3C4D, "
        "estorno até 09/10/2026 ou 2026-10-09, rastreio BR6B8CC1D87BR.",
        structured,
    )
    assert ok, missing


def test_grounding_flags_invented_ids_amounts_and_dates() -> None:
    ok, missing = grounded("Protocolo CAN-FFFFFFFF, valor R$ 10,00, prazo 01/12.", [PROFILE])
    assert not ok
    assert missing == ["date_md:12-01", "id:CAN-FFFFFFFF", "money:10.0"]
    assert answer_facts("sem fatos verificáveis") == set()


def test_score_turn_success_and_arg_mismatch() -> None:
    good = _rec([_call("cancel_order", {"order_id": "o0001"})])
    assert score_turn(good, EXPECTED, SCHEMAS)["e2e_success"] == 1.0
    wrong = score_turn(
        _rec([_call("cancel_order", {"order_id": "O0002"}, status="error")]), EXPECTED, SCHEMAS
    )
    assert wrong["tool_correct"] == 1.0 and wrong["args_valid"] == 0.0
    assert wrong["e2e_success"] == 0.0
    bad_schema = score_turn(
        _rec([_call("cancel_order", {"order_id": "O0001", "x": 1})]), EXPECTED, SCHEMAS
    )
    assert bad_schema["args_valid"] == 0.0


CLARIFY = {
    "status": "error",
    "code": "VALIDATION_ERROR",
    "recoverable": True,
    "message": "O cliente tem 3 pedidos; informe order_id.",
    "details": {"options": ["O0001", "O0002", "O0003"]},
}
NO_ORDER = {**EXPECTED, "args": {}}


def test_clarification_counts_as_e2e_success() -> None:
    asked = _rec(
        [_call("cancel_order", status="error", structured=CLARIFY)],
        answer="Qual pedido você quer cancelar: O0001, O0002 ou O0003?",
    )
    assert score_turn(asked, NO_ORDER, SCHEMAS)["e2e_success"] == 1.0
    completed = _rec([_call("cancel_order", {"order_id": "O0002"})])
    assert score_turn(completed, NO_ORDER, SCHEMAS)["e2e_success"] == 1.0


def test_clarification_requires_offering_the_options() -> None:
    silent = _rec(
        [_call("cancel_order", status="error", structured=CLARIFY)],
        answer="Não consegui cancelar agora, tente mais tarde.",
    )
    assert score_turn(silent, NO_ORDER, SCHEMAS)["e2e_success"] == 0.0
    # the user named the order: a validation error is a failure, not a clarification
    named = _rec(
        [_call("cancel_order", status="error", structured=CLARIFY)],
        answer="Qual pedido: O0001, O0002 ou O0003?",
    )
    assert score_turn(named, EXPECTED, SCHEMAS)["e2e_success"] == 0.0
    not_found = {**CLARIFY, "code": "NOT_FOUND"}
    wrong_code = _rec(
        [_call("cancel_order", status="error", structured=not_found)],
        answer="Qual pedido: O0001, O0002 ou O0003?",
    )
    assert score_turn(wrong_code, NO_ORDER, SCHEMAS)["e2e_success"] == 0.0


def test_escalation_counts_as_abstention() -> None:
    exp = {
        "acceptable_skills": ["__abstain__", "__global__"],
        "acceptable_tools": ["__abstain__", "escalate_to_human"],
        "args": {},
    }
    rec = _rec([_call("escalate_to_human", skill="__global__")], native=True)
    s = score_turn(rec, exp, {"escalate_to_human": {"type": "object"}})
    assert chosen_skill(rec) == "__global__"
    assert s["abstain_correct"] == s["skill_correct"] == s["e2e_success"] == 1.0
    # acting on an out-of-scope request is the failure abstain_correct catches
    acted = score_turn(_rec([_call("cancel_order")]), exp, SCHEMAS)
    assert acted["abstain_correct"] == 0.0


def test_native_skill_is_the_first_loaded_skill() -> None:
    rec = _rec(
        [_call("load_skill", {"skill": "trocas_devolucoes"}), _call("cancel_order")], native=True
    )
    assert chosen_skill(rec) == "trocas_devolucoes"
    assert chosen_skill(_rec([], native=True)) == "__abstain__"


def _shadow(choice: str | None, conf: float, strategy: str, cost: float = 0.0) -> dict[str, Any]:
    return {
        "choice": choice,
        "confidence": conf,
        "candidates": [],
        "strategy": strategy,
        "latency_ms": 10.0,
        "cost_usd": cost,
        "usage": {},
        "cached": False,
    }


def _result_row(
    case: str, regex: tuple[str | None, float], llm: str, *, rep: int = 1, error: str | None = None
) -> dict[str, Any]:
    skill_shadow = {"regex": _shadow(*regex, "regex"), "llm": _shadow(llm, 0.9, "llm", 0.001)}
    return {
        "run_name": "e9-shadow",
        "config": "e9",
        "mode": "routing-only",
        "case_id": case,
        "rep": rep,
        "error": error,
        "expected": {
            "acceptable_skills": ["pedidos_logistica"],
            "acceptable_tools": ["get_order_status"],
        },
        "skill": {"choice": llm, "shadow": skill_shadow},
        "tool": {
            "choice": "get_order_status",
            "shadow": {
                "regex": _shadow("get_order_status", 0.95, "regex"),
                "llm": _shadow("track_shipment", 0.9, "llm", 0.002),
            },
        },
        "scores": {"skill_correct": 1.0, "tool_correct": 1.0, "resolved_by": "llm"},
        "cost_usd": {"routing": 0.003, "agent": 0.0, "total": 0.003},
        "latency_ms": {"turn": 100.0, "routing": 20.0},
    }


def _write_rescored(path: Path, rows: list[dict[str, Any]]) -> None:
    """Reports and simulate read rescored files only: provenance line + rows."""
    head = json.dumps({"_provenance": {"scorer_hash": "test"}})
    path.write_text("\n".join([head, *(json.dumps(r) for r in rows)]))


def test_simulate_replays_cascade_thresholds(tmp_path: Path) -> None:
    path = tmp_path / "shadow.jsonl"
    rows = [
        _result_row("a", ("pedidos_logistica", 0.95), "pedidos_logistica"),
        _result_row("b", ("pagamentos_reembolsos", 0.5), "pedidos_logistica"),
    ]
    _write_rescored(path, rows)
    stage = StageConfig(
        pipeline=[PipelineStep(strategy="regex", min_confidence=0.9), PipelineStep(strategy="llm")]
    )
    settings = Settings(
        _env_file=None,
        experiment_id="sim",
        routing=RoutingConfig(mode="cascade", skill=stage, tool=stage),
    )
    out = simulate(path, settings)
    assert out["skill_acc"] == 1.0  # b: regex below threshold -> llm decides correctly
    assert out["resolved_by"] == {"regex": 1, "llm": 1}
    assert out["joint_acc"] == 1.0 and out["covered_n"] == 2  # regex 0.95 decides the tool
    assert abs(out["routing_cost_case"] - 0.0005) < 1e-9  # only b paid the llm skill step


def test_report_summarizes_per_run(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    rows = [_result_row("a", ("x", 1.0), "y"), _result_row("b", ("x", 1.0), "y", error="boom")]
    _write_rescored(path, rows)
    [row] = summarize(rows)
    # F2 (ITT): the error row counts as wrong
    assert row["n"] == 2 and row["errors"] == 1 and row["skill_correct"] == [1.0, 0.0]
    assert "e9-shadow" in render([path])


def test_load_cases_interleaves_categories(tmp_path: Path) -> None:
    rows = [
        {
            "id": f"{c}{i}",
            "category": c,
            "customer_id": "C001",
            "turns": [{"role": "user", "content": "x"}],
            "expected": {"acceptable_skills": ["__global__"], "acceptable_tools": ["x"]},
        }
        for c in ("a", "b")
        for i in range(3)
    ]
    (tmp_path / "dataset_dev.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    ids = [c.id for c in load_cases("dev", None, data_dir=tmp_path)]
    assert ids == ["a0", "b0", "a1", "b1", "a2", "b2"]
    assert [c.id[0] for c in load_cases("dev", 4, data_dir=tmp_path)] == ["a", "b", "a", "b"]


def test_e2e_counts_business_refusal_as_executed() -> None:
    call = _call("cancel_order", {"order_id": "O0001"}, status="error")
    call["structured"] = {"status": "error", "code": "NOT_ELIGIBLE", "recoverable": False}
    exp = {
        "acceptable_skills": ["pedidos_logistica"],
        "acceptable_tools": ["cancel_order"],
        "args": {"order_id": "O0001"},
    }
    assert score_turn(_rec([call]), exp, SCHEMAS)["e2e_success"] == 1.0


def _not_eligible(order_id: str | None) -> dict[str, Any]:
    call = _call("cancel_order", {"order_id": order_id} if order_id else {}, status="error")
    call["structured"] = {"status": "error", "code": "NOT_ELIGIBLE", "recoverable": False}
    return call


def test_a1_refusal_counts_only_for_an_order_the_user_referred_to() -> None:
    three = {**PROFILE, "orders": [{"order_id": o} for o in ("O0001", "O0002", "O0003")]}
    user = [{"role": "user", "content": "quero cancelar o pedido O0002"}]
    no_id = [{"role": "user", "content": "quero cancelar meu pedido"}]

    def e2e(call: dict[str, Any], turns: list[dict[str, str]], profile: dict[str, Any]) -> Any:
        rec = {**_rec([call]), "customer": profile}
        return score_turn(rec, NO_ORDER, SCHEMAS, turns=turns)["e2e_success"]

    # gold names no order: a refusal on an arbitrary order is not a finished task
    assert e2e(_not_eligible("O0003"), no_id, three) == 0.0
    # the order the user named in the conversation (normalized like the server: 2 -> O0002)
    assert e2e(_not_eligible("O0002"), user, three) == 1.0
    assert e2e(_not_eligible("o0002"), user, three) == 1.0
    assert e2e(_not_eligible("O0003"), user, three) == 0.0
    # single-order customer: that order is the one the user means, named or omitted
    one = {**PROFILE, "orders": [{"order_id": "O0001"}]}
    assert e2e(_not_eligible("O0001"), no_id, one) == 1.0
    assert e2e(_not_eligible(None), no_id, one) == 1.0


ESC_SCHEMAS = {**SCHEMAS, "escalate_to_human": {"type": "object"}}
OUT_OF_SCOPE = {
    "acceptable_skills": ["__abstain__"],
    "acceptable_tools": ["__abstain__"],
    "args": {},
}


def test_a2_escalation_satisfies_out_of_scope_gold_uniformly() -> None:
    esc = _call("escalate_to_human", {"reason": "fora do escopo"}, skill="__global__")
    for rec in (
        _rec([esc], native=True),
        _rec([esc], skill="__global__"),
        _rec([esc], skill=None),
        _rec([esc, esc], native=True),
    ):
        s = score_turn(rec, OUT_OF_SCOPE, ESC_SCHEMAS)
        assert s["skill_correct"] == s["tool_correct"] == s["abstain_correct"] == 1.0, s
        assert s["e2e_success"] == 1.0, s
    # routing-only: the tool router chose escalation
    ro = {
        **_rec([], skill="__global__"),
        "mode": "routing-only",
        "tool": {"choice": "escalate_to_human", "abstained": False},
    }
    s = score_turn(ro, OUT_OF_SCOPE, ESC_SCHEMAS)
    assert s["skill_correct"] == s["tool_correct"] == s["abstain_correct"] == 1.0
    # escalating after a business action is not an abstention
    mixed = score_turn(_rec([_call("cancel_order"), esc], native=True), OUT_OF_SCOPE, ESC_SCHEMAS)
    assert mixed["tool_correct"] == mixed["abstain_correct"] == mixed["e2e_success"] == 0.0
    # an in-scope gold still requires the business tool
    assert score_turn(_rec([esc], native=True), EXPECTED, ESC_SCHEMAS)["tool_correct"] == 0.0


def test_a2_abstain_correct_accepts_escalation_listed_in_acceptable_tools() -> None:
    exp = {
        "acceptable_skills": ["pedidos_logistica", "__global__"],
        "acceptable_tools": ["get_order_status", "escalate_to_human"],
        "args": {},
    }
    esc = _call("escalate_to_human", {"reason": "cliente quer humano"}, skill="__global__")
    assert score_turn(_rec([esc], native=True), exp, ESC_SCHEMAS)["abstain_correct"] == 1.0
    acted = score_turn(_rec([_call("get_order_status")]), exp, ESC_SCHEMAS)
    assert acted["abstain_correct"] == 1.0
    # abstaining when only a business tool is acceptable is still wrong
    host = _rec([], skill=None, outcome="abstained")
    assert score_turn(host, EXPECTED, SCHEMAS)["abstain_correct"] == 0.0


ADDR_SCHEMA = {
    "type": "object",
    "properties": {
        k: {"type": "string"}
        for k in (
            "street",
            "number",
            "complement",
            "neighborhood",
            "city",
            "state",
            "postal_code",
            "order_id",
        )
    },
}
A3_SCHEMAS = {
    "update_delivery_address": ADDR_SCHEMA,
    "search_help_center": {"type": "object", "properties": {"query": {"type": "string"}}},
    "get_payment_status": {"type": "object", "properties": {"order_id": {"type": "string"}}},
}


def _args_ok(tool: str, gold: dict[str, Any], args: dict[str, Any]) -> Any:
    exp = {"acceptable_skills": ["x"], "acceptable_tools": [tool], "args": gold}
    return score_turn(_rec([_call(tool, args)]), exp, A3_SCHEMAS)["args_valid"]


def test_a3_address_gold_matches_the_address_fields() -> None:
    gold = {
        "order_id": "O0001",
        "address": "R. Sete de Setembro, 200, Loja 1, Centro, Florianópolis, SC, CEP 88010-000",
    }
    args = {
        "order_id": "O0001",
        "street": "Rua Sete de Setembro",
        "number": "200",
        "neighborhood": "Centro",
        "city": "Florianopolis",
        "state": "SC",
        "postal_code": "88010000",
    }
    assert _args_ok("update_delivery_address", gold, args) == 1.0
    assert _args_ok("update_delivery_address", gold, {**args, "number": "201"}) == 0.0
    assert _args_ok("update_delivery_address", gold, {**args, "postal_code": "88010-001"}) == 0.0
    assert _args_ok("update_delivery_address", gold, {**args, "street": "Rua Sete"}) == 1.0
    assert _args_ok("update_delivery_address", gold, {**args, "street": "Av. Brasil"}) == 0.0
    # gold without CEP: postal code is not compared
    assert (
        _args_ok(
            "update_delivery_address",
            {"address": "Rua das Flores, 123, Curitiba"},
            {**args, "street": "Rua das Flores", "number": "123"},
        )
        == 1.0
    )


def test_a3_query_is_fuzzy_and_non_parameters_are_ignored() -> None:
    gold = {"query": "política de trocas e devoluções"}
    assert _args_ok("search_help_center", gold, {"query": "Politica de devolucoes"}) == 1.0
    assert _args_ok("search_help_center", gold, {"query": "prazo de entrega"}) == 0.0
    # payment_method is not a get_payment_status parameter: never compared
    assert _args_ok("get_payment_status", {"payment_method": "pix"}, {}) == 1.0
    assert (
        _args_ok(
            "get_payment_status",
            {"payment_method": "pix", "order_id": "O0001"},
            {"order_id": "O0002"},
        )
        == 0.0
    )


def _refused(name: str, skill: str = "pagamentos_reembolsos") -> dict[str, Any]:
    return _call(
        name,
        {"order_id": "O0001"},
        status="refused",
        skill=skill,
        structured={"status": "refused", "code": "TOOL_NOT_AVAILABLE"},
    )


def test_a4_host_refused_calls_are_ignored() -> None:
    calls = [_refused("request_refund"), _call("cancel_order", {"order_id": "O0001"})]
    for rec in (_rec(calls), _rec(calls, native=True)):
        s = score_turn(rec, EXPECTED, SCHEMAS)
        assert chosen_skill(rec) == "pedidos_logistica"
        assert s["tool_correct"] == s["args_valid"] == s["e2e_success"] == 1.0, s
    # only refused calls: nothing was executed
    only = _rec([_refused("cancel_order", "pedidos_logistica")], native=True)
    assert chosen_skill(only) == "__abstain__"
    assert score_turn(only, EXPECTED, SCHEMAS)["tool_correct"] == 0.0


def test_a5_loop_limit_wrap_up_answer_is_grounded() -> None:
    calls = [_call("cancel_order", {"order_id": "O0001"})]
    bad = score_turn(
        _rec(calls, answer="Protocolo CAN-FFFFFFFF.", outcome="loop_limit"), EXPECTED, SCHEMAS
    )
    assert bad["grounded"] == 0.0
    ok = score_turn(_rec(calls, answer="Pedido O0001.", outcome="loop_limit"), EXPECTED, SCHEMAS)
    assert ok["grounded"] == 1.0
    assert (
        score_turn(_rec([], answer="x", outcome="abstained"), EXPECTED, SCHEMAS)["grounded"] is None
    )


def test_a6_successful_retry_after_recoverable_error_counts() -> None:
    retry = [
        _call("cancel_order", status="error", structured=CLARIFY),
        _call("get_order_status"),
        _call("cancel_order", {"order_id": "O0001"}),
    ]
    s = score_turn(_rec(retry, answer="Cancelado."), EXPECTED, SCHEMAS)
    assert s["tool_correct"] == s["args_valid"] == s["e2e_success"] == 1.0, s
    # the scored tool is still the first one called
    first_wrong = [_call("get_order_status"), _call("cancel_order", {"order_id": "O0001"})]
    assert score_turn(_rec(first_wrong), EXPECTED, SCHEMAS)["tool_correct"] == 0.0
    # a failed attempt had no effect: the later completed call reaches the customer's goal
    fatal = {"status": "error", "code": "NOT_FOUND", "recoverable": False}
    final = [
        _call("cancel_order", {"order_id": "O0009"}, status="error", structured=fatal),
        _call("cancel_order", {"order_id": "O0001"}),
    ]
    assert score_turn(_rec(final), EXPECTED, SCHEMAS)["e2e_success"] == 1.0
    # but an action already completed on the wrong target is never rescued
    wrong_done = [
        _call("cancel_order", {"order_id": "O0009"}),
        _call("cancel_order", {"order_id": "O0001"}),
    ]
    assert score_turn(_rec(wrong_done), EXPECTED, SCHEMAS)["e2e_success"] == 0.0


def test_a7_order_and_customer_ids_must_come_from_evidence() -> None:
    profile = {**PROFILE, "customer_id": "C001"}
    assert grounded("Seu pedido O0001 (cliente C001) foi cancelado.", [profile])[0]
    ok, missing = grounded("Seu pedido O0004 foi cancelado.", [profile])
    assert not ok and missing == ["id:O0004"]
    assert grounded("Cliente C002.", [profile]) == (False, ["id:C002"])


def test_a7_thousands_without_cents_and_installments() -> None:
    assert answer_facts("Total R$ 1.299") == {("money", 1299.0)}
    assert grounded("Total R$ 1.299,90 ou R$ 1.299", [{"a": 1299.9, "b": 1299}])[0]
    assert not grounded("Total R$ 1.299", [{"a": 1.3}])[0]
    for text in ("parcela 3/10 de R$ 10,00", "parcelas 2/12", "pago em 3/10x", "3/10 parcelas"):
        assert not {f for f in answer_facts(text) if f[0].startswith("date")}, text
    assert ("date_md", "10-03") in answer_facts("entrega em 03/10")


def test_a13_missing_tool_stage_is_reported_not_silently_cheaper(tmp_path: Path) -> None:
    path = tmp_path / "shadow.jsonl"
    covered = _result_row("a", ("pedidos_logistica", 0.95), "pedidos_logistica")
    # recorded run routed to another skill: its tool decisions are for the wrong skill
    other = _result_row("b", ("pedidos_logistica", 0.95), "pagamentos_reembolsos")
    other["skill"]["choice"] = "pagamentos_reembolsos"
    other["skill"]["shadow"]["regex"]["cost_usd"] = 0.0
    # the recorded run abstained at the skill stage: no tool decisions at all
    abstained = _result_row("c", ("pedidos_logistica", 0.95), "pedidos_logistica")
    abstained["skill"]["choice"], abstained["tool"] = None, None
    covered["tool"]["shadow"]["regex"]["cost_usd"] = 0.01
    _write_rescored(path, [covered, other, abstained])
    stage = StageConfig(
        pipeline=[PipelineStep(strategy="regex", min_confidence=0.9), PipelineStep(strategy="llm")]
    )
    settings = Settings(
        _env_file=None,
        experiment_id="sim",
        routing=RoutingConfig(mode="cascade", skill=stage, tool=stage),
    )
    out = simulate(path, settings)
    assert out["n"] == 3 and out["covered_n"] == 1
    assert out["joint_acc"] == 1 / 3 and out["joint_acc_covered"] == 1.0  # H2 lower bound
    assert out["tool_unavailable"] == 2
    assert abs(out["tool_coverage"] - 1 / 3) < 1e-9
    # cost/latency only over rows whose whole route was simulated
    assert abs(out["routing_cost_case"] - 0.01) < 1e-9
    assert "tool_unavailable=2" in render_simulation(path, settings)


def test_a14_report_splits_routing_and_executor_latency() -> None:
    rows = []
    for i, (rt, ex) in enumerate([(10.0, 100.0), (20.0, 200.0), (30.0, None)]):
        r = _result_row(f"c{i}", ("x", 1.0), "y")
        r["latency_ms"] = {"turn": 5000.0, "routing": rt, **({"executor": ex} if ex else {})}
        rows.append(r)
    [row] = summarize(rows)
    assert row["routing_p50"] == 20.0 and row["routing_p95"] == 29.0
    assert row["executor_p50"] == 150.0 and row["executor_p95"] == 195.0
    assert row["turn_p50"] == 5000.0


def test_a14_executor_timer_counts_only_completed_llm_calls() -> None:
    import time
    from uuid import uuid4

    from routing_study.eval.runner import ExecutorTimer

    timer = ExecutorTimer()
    ok, failed = uuid4(), uuid4()
    timer.on_chat_model_start({}, [[]], run_id=ok)
    timer.on_chat_model_start({}, [[]], run_id=failed)
    time.sleep(0.01)
    timer.on_llm_error(RuntimeError("429"), run_id=failed)
    timer.on_llm_end(None, run_id=ok)  # type: ignore[arg-type]
    assert 10.0 <= timer.ms < 1000.0 and timer.calls == 1


TWO_ORDERS = {"status": "completed", "orders": [{"order_id": "O0001"}, {"order_id": "O0002"}]}
CANCEL = {
    "acceptable_skills": ["pedidos_logistica"],
    "acceptable_tools": ["cancel_order"],
    "args": {},
}


def test_direct_clarification_without_a_call_counts_when_the_tool_was_offered() -> None:
    rec = _rec([], answer="Qual pedido você quer cancelar: O0001 ou O0002?")
    rec |= {"customer": TWO_ORDERS, "exposed_tools": ["cancel_order", "escalate_to_human"]}
    s = score_turn(rec, CANCEL, SCHEMAS)
    assert (s["tool_correct"], s["args_valid"], s["e2e_success"]) == (1.0, 1.0, 1.0)


def test_direct_clarification_fails_when_routing_hid_the_tool_or_order_was_named() -> None:
    rec = _rec([], answer="Qual pedido: O0001 ou O0002?")
    rec |= {"customer": TWO_ORDERS, "exposed_tools": ["escalate_to_human"]}
    assert score_turn(rec, CANCEL, SCHEMAS)["e2e_success"] == 0.0
    rec["exposed_tools"] = ["cancel_order"]
    named = CANCEL | {"args": {"order_id": "O0001"}}
    assert score_turn(rec, named, SCHEMAS)["e2e_success"] == 0.0


def test_e2e_counts_a_later_completed_acceptable_call_but_tool_correct_stays_strict() -> None:
    first = _call("get_order_status", {"order_id": "O0001"})
    later = _call("cancel_order", {"order_id": "O0001"})
    s = score_turn(
        _rec([first, later]),
        CANCEL,
        SCHEMAS | {"get_order_status": SCHEMAS["cancel_order"]},
        read_only={"get_order_status"},
    )
    assert (s["tool_correct"], s["e2e_success"]) == (0.0, 1.0)
