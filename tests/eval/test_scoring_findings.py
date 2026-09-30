"""Shared scorer fixes from .omc/reviews/final-architect.md (H1, H3, M1, M5, L3) and
final-code.md (findings 1 and 7). Each test is named after the finding it covers."""

from __future__ import annotations

from typing import Any

from routing_study.eval.scorers import (
    invented_args,
    routing_scores,
    score_turn,
    tool_index,
)

ORDER_ID = {"anyOf": [{"type": "string"}, {"type": "null"}]}
TOOLS = [
    {
        "name": "cancel_order",
        "inputSchema": {"type": "object", "properties": {"order_id": ORDER_ID}},
        "annotations": {"readOnlyHint": False},
    },
    {
        "name": "get_order_status",
        "inputSchema": {"type": "object", "properties": {"order_id": ORDER_ID}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "fetch_order_details",  # read-only tool whose name has no read verb
        "inputSchema": {"type": "object", "properties": {"order_id": ORDER_ID}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "search_help_center",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "escalate_to_human",
        "inputSchema": {
            "type": "object",
            "required": ["reason"],
            "properties": {"reason": {"type": "string"}, "order_id": ORDER_ID},
        },
        "annotations": {"readOnlyHint": False},
    },
    {
        "name": "open_warranty_claim",
        "inputSchema": {
            "type": "object",
            "required": ["defect_description"],
            "properties": {"defect_description": {"type": "string"}, "order_id": ORDER_ID},
        },
        "annotations": {"readOnlyHint": False},
    },
    {
        "name": "reschedule_delivery",
        "inputSchema": {
            "type": "object",
            "required": ["new_date"],
            "properties": {
                "new_date": {"type": "string"},
                "order_id": ORDER_ID,
                "period": {"enum": ["manha", "tarde"]},
            },
        },
        "annotations": {"readOnlyHint": False},
    },
]
SCHEMAS, READ_ONLY = tool_index(TOOLS)
TWO_ORDERS = {"status": "completed", "orders": [{"order_id": "O0001"}, {"order_id": "O0002"}]}
OUT_OF_SCOPE = {
    "acceptable_skills": ["__abstain__"],
    "acceptable_tools": ["__abstain__"],
    "args": {},
}
WARRANTY = {
    "acceptable_skills": ["trocas_devolucoes"],
    "acceptable_tools": ["open_warranty_claim"],
    "args": {"order_id": "O0001"},
}


def _call(name: str, args: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
    status = kw.get("status", "completed")
    return {
        "name": name,
        "args": args or {},
        "skill": kw.get("skill", "x"),
        "status": status,
        "structured": kw.get("structured") or {"status": status},
    }


def _rec(calls: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    skill = kw.get("skill", "pedidos_logistica")
    return {
        "native": kw.get("native", False),
        "mode": kw.get("mode", "e2e"),
        "calls": calls,
        "outcome": kw.get("outcome", "answered"),
        "final_answer": kw.get("answer", "ok"),
        "customer": kw.get("customer", TWO_ORDERS),
        "exposed_tools": kw.get("exposed", []),
        "skill": {"choice": skill, "abstained": skill is None, "resolved_by": "llm"},
        "tool": {"choice": kw["tool"], "abstained": False} if kw.get("tool") else None,
    }


# ---------------------------------------------------------------- H1


def test_h1_global_escalate_is_a_correct_abstention_for_every_consumer() -> None:
    """The mapping lives in one function: shadow strategies (simulate / study_report) and
    score_turn give the same answer for __global__ -> escalate_to_human."""
    s = routing_scores("__global__", "escalate_to_human", OUT_OF_SCOPE)
    assert s == {
        "skill_correct": 1.0,
        "tool_correct": 1.0,
        "joint_correct": 1.0,
        "abstain_correct": 1.0,
    }
    ro = _rec([], mode="routing-only", skill="__global__", tool="escalate_to_human")
    turn = score_turn(ro, OUT_OF_SCOPE, SCHEMAS)
    assert {k: turn[k] for k in s} == s
    # regex abstaining gets the same credit, and a business skill does not
    assert routing_scores("__abstain__", "__abstain__", OUT_OF_SCOPE)["joint_correct"] == 1.0
    assert routing_scores("pedidos_logistica", "cancel_order", OUT_OF_SCOPE)["joint_correct"] == 0


# ---------------------------------------------------------------- code finding 7


def test_code7_escalation_does_not_rescue_a_wrong_router_skill() -> None:
    esc = _call("escalate_to_human", {"reason": "fora do escopo"}, skill="__global__")
    routed_wrong = score_turn(_rec([esc], skill="pedidos_logistica"), OUT_OF_SCOPE, SCHEMAS)
    assert routed_wrong["skill_correct"] == 0.0 and routed_wrong["tool_correct"] == 1.0
    assert routed_wrong["e2e_success"] == 0.0
    for rec in (_rec([esc], skill="__global__"), _rec([esc], native=True)):
        assert score_turn(rec, OUT_OF_SCOPE, SCHEMAS)["skill_correct"] == 1.0
    ro = _rec([], mode="routing-only", skill="pedidos_logistica", tool="escalate_to_human")
    assert score_turn(ro, OUT_OF_SCOPE, SCHEMAS)["skill_correct"] == 0.0


# ---------------------------------------------------------------- M1 / code finding 1


def test_m1_invented_answer_mentioning_two_orders_gets_no_credit() -> None:
    exp = {
        "acceptable_skills": ["__global__"],
        "acceptable_tools": ["search_help_center"],
        "args": {},
    }
    rec = _rec(
        [],
        skill="__global__",
        answer="Seu pedido O0001 foi entregue ontem e o O0002 está a caminho.",
        exposed=["search_help_center", "escalate_to_human"],
    )
    s = score_turn(rec, exp, SCHEMAS)
    assert s["tool_correct"] == s["e2e_success"] == 0.0


def test_m1_which_order_question_never_credits_escalation_or_abstention() -> None:
    exp = {
        "acceptable_skills": ["__abstain__", "__global__"],
        "acceptable_tools": ["__abstain__", "escalate_to_human"],
        "args": {},
    }
    rec = _rec(
        [],
        skill="__global__",
        answer="Qual pedido, O0001 ou O0002?",
        exposed=["escalate_to_human"],
    )
    s = score_turn(rec, exp, SCHEMAS)
    # no tool ran: tool = __abstain__ (acceptable here), but it is not a clarification credit
    # and, without escalating or a host abstention, not an abstention either (M5)
    assert s["args_valid"] == 1.0
    assert s["abstain_correct"] == 0.0


def test_code1_clarification_must_be_a_question_on_an_order_id_tool() -> None:
    cancel = {"acceptable_skills": ["pedidos_logistica"], "acceptable_tools": ["cancel_order"]}
    cancel |= {"args": {}}
    statement = _rec(
        [], answer="Seus pedidos são O0001 e O0002.", exposed=["cancel_order"], tool="cancel_order"
    )
    assert score_turn(statement, cancel, SCHEMAS)["e2e_success"] == 0.0
    question = {**statement, "final_answer": "Qual pedido quer cancelar: O0001 ou O0002?"}
    assert score_turn(question, cancel, SCHEMAS)["e2e_success"] == 1.0


def test_code1_clarification_credits_the_router_tool_choice_only() -> None:
    exp = {
        "acceptable_skills": ["pedidos_logistica"],
        "acceptable_tools": ["cancel_order", "get_order_status"],
        "args": {},
    }
    ask = "Qual pedido: O0001 ou O0002?"
    exposed = ["cancel_order", "get_order_status", "fetch_order_details"]
    wrong = _rec([], answer=ask, exposed=exposed, tool="fetch_order_details")
    assert score_turn(wrong, exp, SCHEMAS)["tool_correct"] == 0.0
    right = _rec([], answer=ask, exposed=exposed, tool="get_order_status")
    assert score_turn(right, exp, SCHEMAS)["tool_correct"] == 1.0
    native = _rec([], answer=ask, exposed=exposed, native=True)
    assert score_turn(native, exp, SCHEMAS)["tool_correct"] == 1.0


# ---------------------------------------------------------------- H3


def test_h3_invented_required_argument_is_flagged() -> None:
    turns = [{"role": "user", "content": "Preciso abrir garantia do pedido O0001"}]
    invented = _call(
        "open_warranty_claim",
        {"order_id": "O0001", "defect_description": "Fone parou de funcionar"},
        status="error",
        structured={"status": "error", "code": "NOT_ELIGIBLE", "recoverable": False},
    )
    s = score_turn(_rec([invented], skill="trocas_devolucoes"), WARRANTY, SCHEMAS, turns=turns)
    assert s["e2e_success"] == 1.0  # the lenient metric keeps the old definition
    assert s["args_invented"] == 1.0 and s["e2e_strict"] == 0.0
    said = [{"role": "user", "content": "O fone do pedido O0001 parou de funcionar"}]
    s = score_turn(_rec([invented], skill="trocas_devolucoes"), WARRANTY, SCHEMAS, turns=said)
    assert s["args_invented"] == 0.0 and s["e2e_strict"] == 1.0


def test_h3_args_invented_ignores_enums_escalation_reason_and_gold_args() -> None:
    turns = [{"role": "user", "content": "quero remarcar a entrega para amanhã"}]
    call = _call("reschedule_delivery", {"new_date": "2026-10-01", "period": "manha"})
    assert invented_args(call, {"args": {}}, SCHEMAS, turns) == []
    no_hint = [{"role": "user", "content": "quero remarcar a entrega"}]
    assert invented_args(call, {"args": {}}, SCHEMAS, no_hint) == ["new_date"]
    assert invented_args(call, {"args": {"new_date": "2026-10-01"}}, SCHEMAS, no_hint) == []
    esc = _call("escalate_to_human", {"reason": "cliente pediu humano"})
    assert invented_args(esc, {"args": {}}, SCHEMAS, no_hint) == []


def test_h3_asking_for_a_missing_required_field_is_a_correct_clarification() -> None:
    turns = [{"role": "user", "content": "Preciso abrir garantia do pedido O0001"}]
    rec = _rec(
        [],
        skill="trocas_devolucoes",
        answer="Claro! Qual é o defeito que o produto apresenta?",
        exposed=["open_warranty_claim", "escalate_to_human"],
        tool="open_warranty_claim",
    )
    s = score_turn(rec, WARRANTY, SCHEMAS, turns=turns)
    assert (s["tool_correct"], s["args_valid"], s["e2e_success"]) == (1.0, 1.0, 1.0)
    assert s["e2e_strict"] == 1.0 and s["args_invented"] is None
    # a date the customer already gave is not missing: asking for it earns nothing
    resched = {
        "acceptable_skills": ["pedidos_logistica"],
        "acceptable_tools": ["reschedule_delivery"],
        "args": {"order_id": "O0001"},
    }
    ask_date = {
        **rec,
        "final_answer": "Para qual data você quer remarcar?",
        "exposed_tools": ["reschedule_delivery"],
        "tool": {"choice": "reschedule_delivery"},
        "skill": {"choice": "pedidos_logistica", "resolved_by": "llm"},
    }
    no_date = [{"role": "user", "content": "quero remarcar a entrega do O0001"}]
    assert score_turn(ask_date, resched, SCHEMAS, turns=no_date)["e2e_success"] == 1.0
    gave = [{"role": "user", "content": "quero remarcar a entrega do O0001 para sexta"}]
    assert score_turn(ask_date, resched, SCHEMAS, turns=gave)["e2e_success"] == 0.0


# ---------------------------------------------------------------- M5


def test_m5_e2e_abstention_is_host_abstention_or_escalation_only() -> None:
    cancel = {"acceptable_skills": ["pedidos_logistica"], "acceptable_tools": ["cancel_order"]}
    cancel |= {"args": {}}
    clarifying = _rec([], answer="Qual pedido: O0001 ou O0002?", exposed=[], tool="cancel_order")
    assert score_turn(clarifying, cancel, SCHEMAS)["abstain_correct"] == 1.0
    host = _rec([], skill=None, outcome="abstained", answer=None)
    assert score_turn(host, cancel, SCHEMAS)["abstain_correct"] == 0.0
    assert score_turn(host, OUT_OF_SCOPE, SCHEMAS)["abstain_correct"] == 1.0


# ---------------------------------------------------------------- L3


def test_l3_read_only_comes_from_the_readonlyhint_annotation() -> None:
    assert "fetch_order_details" in READ_ONLY and "cancel_order" not in READ_ONLY
    cancel = {"acceptable_skills": ["pedidos_logistica"], "acceptable_tools": ["cancel_order"]}
    cancel |= {"args": {"order_id": "O0001"}}
    calls = [
        _call("fetch_order_details", {"order_id": "O0001"}),
        _call("cancel_order", {"order_id": "O0001"}),
    ]
    ok = score_turn(_rec(calls), cancel, SCHEMAS, read_only=READ_ONLY)
    assert ok["e2e_success"] == 1.0
    # without the annotation the earlier completed call is an action: never rescued
    assert score_turn(_rec(calls), cancel, SCHEMAS, read_only=frozenset())["e2e_success"] == 0.0


# ---------------------------------------------------------------- F5 (methodology-final M5)

CLARIFY_3 = {
    "status": "error",
    "code": "VALIDATION_ERROR",
    "recoverable": True,
    "details": {"options": ["O0001", "O0002", "O0003"]},
}
CANCEL_ANY = {
    "acceptable_skills": ["pedidos_logistica"],
    "acceptable_tools": ["cancel_order"],
    "args": {},
}


def test_f5_asked_which_order_needs_a_question_two_ids_and_no_success_claim() -> None:
    from routing_study.eval.scorers import asked_which_order

    call = _call("cancel_order", status="error", structured=CLARIFY_3)
    assert asked_which_order(call, CANCEL_ANY, "Qual pedido quer cancelar: O0001 ou O0002?")
    # a statement offering the ids is not a question
    assert not asked_which_order(call, CANCEL_ANY, "Seus pedidos são O0001 e O0002.")
    # one id offered is not a choice
    assert not asked_which_order(call, CANCEL_ANY, "Quer cancelar o O0001?")
    # claims it already acted
    assert not asked_which_order(
        call, CANCEL_ANY, "Pronto, o pedido O0001 foi cancelado! Quer cancelar o O0002 também?"
    )


def test_f5_direct_which_order_clarification_rejects_a_success_claim() -> None:
    rec = _rec(
        [],
        answer="Já cancelei o O0001. Deseja algo com o O0002?",
        exposed=["cancel_order"],
        tool="cancel_order",
    )
    assert score_turn(rec, CANCEL_ANY, SCHEMAS)["e2e_success"] == 0.0


def test_f5_missing_required_checks_free_text_fields_against_the_user_turns() -> None:
    from routing_study.eval.scorers import missing_required

    exp = {"acceptable_tools": ["open_warranty_claim"], "args": {"order_id": "O0001"}}
    said = [{"role": "user", "content": "o fone do pedido O0001 parou de funcionar"}]
    assert missing_required("open_warranty_claim", exp, SCHEMAS, said) == []
    silent = [{"role": "user", "content": "quero abrir garantia do pedido O0001"}]
    assert missing_required("open_warranty_claim", exp, SCHEMAS, silent) == ["defect_description"]


def test_f5_clarification_credit_needs_the_field_asked_in_a_question() -> None:
    turns = [{"role": "user", "content": "Preciso abrir garantia do pedido O0001"}]
    base = dict(skill="trocas_devolucoes", exposed=["open_warranty_claim"])
    base |= {"tool": "open_warranty_claim"}
    stray = _rec(
        [], answer="Entendi o problema. Posso ajudar com mais alguma coisa?", **base
    )  # keyword "problema" outside the question
    assert score_turn(stray, WARRANTY, SCHEMAS, turns=turns)["e2e_success"] == 0.0
    asked = _rec([], answer="Entendi. Qual defeito o produto apresenta?", **base)
    assert score_turn(asked, WARRANTY, SCHEMAS, turns=turns)["e2e_success"] == 1.0
    # the customer already described the defect: asking again earns nothing
    said = [{"role": "user", "content": "abrir garantia do O0001, a tela quebrou"}]
    assert score_turn(asked, WARRANTY, SCHEMAS, turns=said)["e2e_success"] == 0.0


def test_f5_call_args_valid_enforces_order_ids_the_user_wrote() -> None:
    from routing_study.eval.scorers import call_args_valid

    turns = [{"role": "user", "content": "quero cancelar o pedido O0002"}]
    wrong = _call("cancel_order", {"order_id": "O0001"})
    right = _call("cancel_order", {"order_id": "o0002"})
    assert not call_args_valid(wrong, CANCEL_ANY, SCHEMAS, turns)
    assert call_args_valid(right, CANCEL_ANY, SCHEMAS, turns)
    assert call_args_valid(wrong, CANCEL_ANY, SCHEMAS, None)  # no user id: not enforced
    s = score_turn(_rec([wrong]), CANCEL_ANY, SCHEMAS, turns=turns)
    assert s["args_valid"] == 0.0 and s["e2e_success"] == 0.0


def test_f5_native_skill_is_the_skill_loaded_after_a_global_tool() -> None:
    from routing_study.eval.scorers import chosen_skill

    search = _call("search_help_center", {"query": "prazo"}, skill="__global__")
    load = _call("load_skill", {"skill": "trocas_devolucoes"})
    assert chosen_skill(_rec([search, load], native=True)) == "trocas_devolucoes"
    assert chosen_skill(_rec([search], native=True)) == "__global__"
    assert chosen_skill(_rec([], native=True)) == "__abstain__"


# ---------------------------------------------------------------- F6


def test_f6_e2e_decomposition_partitions_e2e_success() -> None:
    cancel = CANCEL_ANY | {"args": {"order_id": "O0001"}}
    first = score_turn(_rec([_call("cancel_order", {"order_id": "O0001"})]), cancel, SCHEMAS)
    clar = score_turn(
        _rec(
            [],
            answer="Qual pedido quer cancelar: O0001 ou O0002?",
            exposed=["cancel_order"],
            tool="cancel_order",
        ),
        CANCEL_ANY,
        SCHEMAS,
    )
    rec_calls = [
        _call("get_order_status", {"order_id": "O0001"}),
        _call("cancel_order", {"order_id": "O0001"}),
    ]
    recovered = score_turn(_rec(rec_calls), cancel, SCHEMAS, read_only=READ_ONLY)
    parts = ("first_call_success", "clarification_credited", "recovered_credited")
    assert [first[k] for k in parts] == [1.0, 0.0, 0.0]
    assert [clar[k] for k in parts] == [0.0, 1.0, 0.0]
    assert [recovered[k] for k in parts] == [0.0, 0.0, 1.0]
    for s in (first, clar, recovered):
        assert sum(s[k] for k in parts) == s["e2e_success"] == 1.0
        assert s["entity_grounded"] == s["grounded"]  # alias kept for old rows


def test_f6_first_label_only_is_a_stricter_sensitivity() -> None:
    exp = {
        "acceptable_skills": ["trocas_devolucoes", "pedidos_logistica"],
        "acceptable_tools": ["create_return_request", "cancel_order"],
        "args": {},
    }
    ro = _rec([], mode="routing-only", skill="pedidos_logistica", tool="cancel_order")
    s = score_turn(ro, exp, SCHEMAS)
    assert s["joint_correct"] == 1.0 and s["joint_first_label"] == 0.0
    oos = _rec([], mode="routing-only", skill="__global__", tool="escalate_to_human")
    assert score_turn(oos, OUT_OF_SCOPE, SCHEMAS)["joint_first_label"] == 1.0
