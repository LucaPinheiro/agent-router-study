"""Scores (plan §6.3) computed from one turn record (see `runner.turn_record`).

`__abstain__` stands for "no action": a routed abstention, or no business tool called.
Escalating to a human is the abstention behaviour (D4), so it counts as abstaining.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from routing_study.eval.grounding import grounded
from routing_study.routers.base import ABSTAIN, GLOBAL_OPTION

LOAD_SKILL = "load_skill"
ESCALATE = "escalate_to_human"


def business_calls(rec: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in rec.get("calls", []) if c["name"] != LOAD_SKILL]


def first_call(rec: dict[str, Any]) -> dict[str, Any] | None:
    calls = business_calls(rec)
    return calls[0] if calls else None


def chosen_skill(rec: dict[str, Any]) -> str:
    if not rec["native"]:
        skill = rec.get("skill") or {}
        return ABSTAIN if skill.get("abstained") or not skill.get("choice") else skill["choice"]
    for c in rec.get("calls", []):  # native: the first skill it loaded, else the tool's skill
        if c["name"] == LOAD_SKILL and c["args"].get("skill"):
            return c["args"]["skill"]
        if c["name"] != LOAD_SKILL:
            return c.get("skill") or GLOBAL_OPTION
    return ABSTAIN


def chosen_tool(rec: dict[str, Any]) -> str:
    if rec["mode"] == "routing-only":
        tool = rec.get("tool") or {}
        return tool["choice"] if tool.get("choice") and not tool.get("abstained") else ABSTAIN
    call = first_call(rec)
    return call["name"] if call else ABSTAIN


def _match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().casefold() == actual.strip().casefold()
    return expected == actual


def args_valid(rec: dict[str, Any], expected: dict[str, Any],
               schemas: dict[str, dict[str, Any]]) -> bool:
    call = first_call(rec)
    if call is None:
        return ABSTAIN in expected["acceptable_tools"]
    schema = schemas.get(call["name"])
    if schema is None or any(True for _ in Draft202012Validator(schema).iter_errors(call["args"])):
        return False
    return all(_match(v, call["args"].get(k)) for k, v in (expected.get("args") or {}).items())


def expects_abstention(expected: dict[str, Any]) -> bool:
    tools = set(expected["acceptable_tools"])
    return ABSTAIN in tools or tools <= {ESCALATE}


def asked_which_order(call: dict[str, Any] | None, expected: dict[str, Any],
                      answer: str | None) -> bool:
    """Correct clarification: the user named no order, the customer has several, the tool
    answered a recoverable VALIDATION_ERROR listing them and the reply offers them back."""
    if call is None or "order_id" in (expected.get("args") or {}) or not answer:
        return False
    err = call.get("structured") or {}
    options = (err.get("details") or {}).get("options") or []
    if not (err.get("code") == "VALIDATION_ERROR" and err.get("recoverable")
            and len(options) > 1):
        return False
    text = answer.casefold()
    return any(str(o).casefold() in text for o in options)


def score_turn(rec: dict[str, Any], expected: dict[str, Any],
               schemas: dict[str, dict[str, Any]]) -> dict[str, float | str | None]:
    """name -> value (None = not applicable for this turn/mode)."""
    skill, tool = chosen_skill(rec), chosen_tool(rec)
    scores: dict[str, float | str | None] = {
        "skill_correct": float(skill in expected["acceptable_skills"]),
        "tool_correct": float(tool in expected["acceptable_tools"]),
        "abstain_correct": float(expects_abstention(expected) == (tool in (ABSTAIN, ESCALATE))),
        "resolved_by": ("native" if rec["native"]
                        else (rec.get("skill") or {}).get("resolved_by") or "abstained"),
    }
    if rec["mode"] == "routing-only":
        return scores | {"args_valid": None, "e2e_success": None, "grounded": None}
    args_ok = args_valid(rec, expected, schemas)
    call = first_call(rec)
    scores["args_valid"] = float(args_ok)
    answer = rec.get("final_answer")
    # The server ran the right tool: completed, a business refusal that depends on the mock
    # fixture's order state (NOT_ELIGIBLE), or a correct "which order?" clarification.
    finished = (call is None or call["status"] == "completed"
                or (call.get("structured") or {}).get("code") == "NOT_ELIGIBLE"
                or asked_which_order(call, expected, answer))
    scores["e2e_success"] = float(bool(scores["skill_correct"]) and bool(scores["tool_correct"])
                                  and args_ok and finished)
    if rec.get("outcome") == "answered" and answer:
        evidence = [rec.get("customer"), *(c.get("structured") for c in business_calls(rec))]
        scores["grounded"] = float(grounded(answer, [e for e in evidence if e])[0])
    else:
        scores["grounded"] = None
    return scores
