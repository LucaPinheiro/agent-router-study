"""Symmetric e2e scorer (plan T1.1): same behaviour -> same score, whatever the arm."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from routing_study.eval.rescore import load_dataset, load_tools, read_rescored
from routing_study.eval.scorers import score_turn, scorer_hash, tool_index
from routing_study.eval.scorers_sym import score_turn_sym, scorer_sym_hash, tool_skills

ROOT = Path(__file__).resolve().parents[2]
TOOLS = load_tools(ROOT / "mcp_server" / "tools_list.json")
SCHEMAS, READ_ONLY = tool_index(TOOLS)
SKILLS = tool_skills(TOOLS)
PHASE1_E2E = sorted((ROOT / "results" / "rescored").glob("v2-*-e2e-*.jsonl"))

OUT_OF_SCOPE = {
    "acceptable_skills": ["__abstain__"],
    "acceptable_tools": ["__abstain__", "escalate_to_human"],
    "args": {},
}


def sym(rec: dict[str, Any], expected: dict[str, Any], turns=None) -> dict[str, Any]:
    return score_turn_sym(rec, expected, SCHEMAS, turns, READ_ONLY, SKILLS)


def legacy(rec: dict[str, Any], expected: dict[str, Any], turns=None) -> dict[str, Any]:
    return score_turn(rec, expected, SCHEMAS, turns, READ_ONLY)


def call(name: str, status: str = "completed", **args: Any) -> dict[str, Any]:
    return {"name": name, "args": args, "skill": SKILLS.get(name), "status": status}


def routed(calls: list[dict[str, Any]], answer: str | None, label: str, **kw: Any) -> dict:
    """A routed e2e record whose router labelled `label` (skill) and its first tool."""
    return {
        "mode": "e2e",
        "native": False,
        "outcome": "answered",
        "final_answer": answer,
        "calls": calls,
        "customer": None,
        "exposed_tools": ["escalate_to_human", "get_customer_profile", "search_help_center"],
        "skill": {"choice": label, "abstained": False, "resolved_by": "llm"},
        "tool": {"choice": "track_shipment", "abstained": False},
        **kw,
    }


def native(calls: list[dict[str, Any]], answer: str | None, **kw: Any) -> dict:
    return {
        "mode": "e2e",
        "native": True,
        "outcome": "answered",
        "final_answer": answer,
        "calls": calls,
        "customer": None,
        "exposed_tools": [t["name"] for t in TOOLS],
        "skill": None,
        "tool": None,
        **kw,
    }


def neutralized(rec: dict[str, Any]) -> dict[str, Any]:
    """The same behaviour with the arm flipped and every router record stripped."""
    out = copy.deepcopy(rec)
    out["native"] = not rec["native"]
    out["skill"] = None
    out["tool"] = None
    return out


# ------------------------------------------------------------------ identical calls


def test_identical_calls_identical_score_across_arms() -> None:
    """Phase-1 class A1: both executors decline an out-of-scope request without a call.
    Legacy: the router's `__global__` label fails the routed turn and native passes. Sym:
    the same behaviour gives the same score in both arms."""
    answer = "Desculpe, não consigo ajudar com isso por aqui."
    r = routed([], answer, "__global__")
    n = native([], answer)
    assert legacy(r, OUT_OF_SCOPE)["e2e_success"] == 0.0
    assert legacy(n, OUT_OF_SCOPE)["e2e_success"] == 1.0
    assert sym(r, OUT_OF_SCOPE) == sym(n, OUT_OF_SCOPE)
    assert sym(r, OUT_OF_SCOPE)["e2e_success"] == 1.0


def test_identical_business_calls_identical_score_load_skill_ignored() -> None:
    exp = {
        "acceptable_skills": ["pagamentos_reembolsos"],
        "acceptable_tools": ["get_refund_status"],
        "args": {"order_id": "O0010"},
    }
    calls = [call("get_refund_status", order_id="O0010")]
    load = {"name": "load_skill", "args": {"skill": "pagamentos_reembolsos"}, "status": "completed"}
    answer = "Seu reembolso do pedido O0010 está em processamento."
    r = routed(calls, answer, "pedidos_logistica")  # wrong router label
    n = native([load, *calls], answer)
    assert legacy(r, exp)["e2e_success"] == 0.0
    assert sym(r, exp) == sym(n, exp)
    assert sym(r, exp)["e2e_success"] == 1.0
    assert sym(r, exp)["skill_attributed"] == "pagamentos_reembolsos"


@pytest.mark.skipif(not PHASE1_E2E, reason="phase-1 results not present (gitignored)")
@pytest.mark.parametrize("path", PHASE1_E2E, ids=lambda p: p.stem)
def test_invariance_on_every_phase1_e2e_row(path: Path) -> None:
    """Spec T1.1 test 1: flipping `native` and stripping the router's skill/tool records
    never changes the symmetric score of a recorded phase-1 row."""
    _, rows = read_rescored(path)
    cases, _ = load_dataset(rows[0]["split"], ROOT / "data")
    for row in rows:
        if "calls" not in row:
            continue
        case = cases[row["case_id"]]
        a = sym(row, case["expected"], case["turns"])
        b = sym(neutralized(row), case["expected"], case["turns"])
        assert a == b, row["case_id"]


@pytest.mark.skipif(not PHASE1_E2E, reason="phase-1 results not present (gitignored)")
def test_native_rows_replayed_as_routed_keep_their_score() -> None:
    """Every E0 turn replayed as a routed turn (no load_skill, a wrong router label, the
    router's top-2 exposure) with the SAME business calls and reply scores the same."""
    path = ROOT / "results" / "rescored" / "v2-e0-native-e2e-r1.jsonl"
    _, rows = read_rescored(path)
    cases, _ = load_dataset("test_v2", ROOT / "data")
    for row in rows:
        case = cases[row["case_id"]]
        twin = copy.deepcopy(row)
        twin["native"] = False
        twin["calls"] = [c for c in row["calls"] if c["name"] != "load_skill"]
        twin["skill"] = {"choice": "__global__", "abstained": False, "resolved_by": "llm"}
        twin["tool"] = {"choice": "escalate_to_human", "abstained": False}
        twin["exposed_tools"] = ["escalate_to_human"]
        assert sym(twin, case["expected"], case["turns"]) == sym(
            row, case["expected"], case["turns"]
        ), row["case_id"]


# ------------------------------------------------------------------ hand cases

ADDRESS = {
    "acceptable_skills": ["pedidos_logistica"],
    "acceptable_tools": ["update_delivery_address"],
    "args": {"order_id": "O0010"},
}
ADDRESS_TURNS = [{"role": "user", "content": "Quero mudar o endereço de entrega do pedido O0010"}]
ASK_ADDRESS = "Claro! Qual é o novo endereço de entrega, com CEP?"


def test_native_load_skill_without_call_credits_the_clarified_tool() -> None:
    load = {"name": "load_skill", "args": {"skill": "pedidos_logistica"}, "status": "completed"}
    n = native([load], ASK_ADDRESS)
    s = sym(n, ADDRESS, ADDRESS_TURNS)
    assert s["skill_attributed"] == "pedidos_logistica"
    assert s["e2e_success"] == s["clarification_credited"] == 1.0
    # the routed twin is credited too, although its router chose another tool
    r = routed([], ASK_ADDRESS, "pedidos_logistica")
    assert legacy(r, ADDRESS, ADDRESS_TURNS)["e2e_success"] == 0.0
    assert sym(r, ADDRESS, ADDRESS_TURNS) == s


def test_native_load_skill_without_call_or_question_is_an_abstention() -> None:
    load = {"name": "load_skill", "args": {"skill": "pedidos_logistica"}, "status": "completed"}
    s = sym(native([load], "Vou verificar isso para você."), ADDRESS, ADDRESS_TURNS)
    assert s["skill_attributed"] == "__abstain__"
    assert s["e2e_success"] == 0.0


def test_routed_host_abstention() -> None:
    rec = routed([], None, "__abstain__", outcome="abstained")
    rec["skill"] = {"choice": None, "abstained": True}
    out = sym(rec, OUT_OF_SCOPE)
    assert out["skill_attributed"] == "__abstain__"
    assert out["e2e_success"] == out["abstain_correct"] == 1.0
    assert sym(rec, ADDRESS, ADDRESS_TURNS)["e2e_success"] == 0.0


def test_escalation_only_turn_is_an_abstention() -> None:
    rec = native([call("escalate_to_human", reason="pedido fora do escopo")], "Encaminhei.")
    out = sym(rec, OUT_OF_SCOPE)
    assert out["skill_attributed"] == "__abstain__"
    assert out["e2e_success"] == 1.0
    assert sym(neutralized(rec), OUT_OF_SCOPE) == out


def test_global_only_turn() -> None:
    exp = {
        "acceptable_skills": ["__global__"],
        "acceptable_tools": ["get_customer_profile"],
        "args": {},
    }
    rec = routed([call("get_customer_profile")], "Seus dados: ...", "pedidos_logistica")
    out = sym(rec, exp)
    assert out["skill_attributed"] == "__global__"
    assert out["e2e_success"] == 1.0
    assert legacy(rec, exp)["e2e_success"] == 0.0  # legacy reads the router's label


def test_global_call_before_a_skill_tool_does_not_decide_the_skill() -> None:
    exp = {
        "acceptable_skills": ["pagamentos_reembolsos"],
        "acceptable_tools": ["get_refund_status"],
        "args": {},
    }
    rec = native(
        [call("get_customer_profile"), call("get_refund_status", order_id="O0010")], "Pronto."
    )
    out = sym(rec, exp)
    assert out["skill_attributed"] == "pagamentos_reembolsos"
    assert out["e2e_success"] == out["recovered_credited"] == 1.0


def test_recovery_across_skills_keeps_the_first_skill() -> None:
    """Rule 1: the first skill-bound call decides the skill. A later acceptable call in
    another skill does not rescue the turn, in either arm."""
    exp = {
        "acceptable_skills": ["pagamentos_reembolsos"],
        "acceptable_tools": ["get_refund_status"],
        "args": {"order_id": "O0010"},
    }
    calls = [
        call("get_order_status", order_id="O0010"),
        call("get_refund_status", order_id="O0010"),
    ]
    r = routed(calls, "Seu reembolso está em processamento.", "pagamentos_reembolsos")
    out = sym(r, exp)
    assert out["skill_attributed"] == "pedidos_logistica"
    assert out["e2e_success"] == 0.0
    assert sym(neutralized(r), exp) == out
    # same skill: a later acceptable call recovers
    exp2 = exp | {
        "acceptable_skills": ["pedidos_logistica"],
        "acceptable_tools": ["track_shipment"],
    }
    rec2 = routed(
        [call("get_order_status", order_id="O0010"), call("track_shipment", order_id="O0010")],
        "Está a caminho.",
        "pedidos_logistica",
    )
    assert sym(rec2, exp2)["recovered_credited"] == 1.0


def test_refused_calls_and_routing_only_rows() -> None:
    refused = call("cancel_order", status="refused", order_id="O0010")
    out = sym(native([refused], "Não consigo fazer isso."), OUT_OF_SCOPE)
    assert out["skill_attributed"] == "__abstain__"
    ro = {
        "mode": "routing-only",
        "native": False,
        "skill": {"choice": "pedidos_logistica"},
        "tool": {"choice": "track_shipment"},
    }
    exp = {"acceptable_skills": ["pedidos_logistica"], "acceptable_tools": ["track_shipment"]}
    leg = legacy(ro, exp)
    leg.pop("resolved_by")
    assert sym(ro, exp) == leg


def test_hashes() -> None:
    assert scorer_hash() == "e0eef1fb0073"  # the phase-1 scorer is untouched
    assert len(scorer_sym_hash()) == 12 and scorer_sym_hash() != scorer_hash()


def test_sym_rows_are_json_serializable() -> None:
    json.dumps(sym(native([call("get_customer_profile")], "ok"), OUT_OF_SCOPE))
