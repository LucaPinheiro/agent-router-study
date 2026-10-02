"""Symmetric e2e scorer (prereg-v2 §4, spec R4): `e2e_success_sym`.

The pre-registered phase-1 scorer (`scorers.score_turn`) attributes the e2e skill differently
per arm: the ROUTER's label in a routed run, and the agent's behaviour (`load_skill`) in the
native run. So two turns with the same business calls could get different verdicts (phase 1:
22 of the 40 E0-only wins). This module scores both arms with ONE function of behaviour. It
never reads `rec["native"]`, the router's `skill` / `tool` records or `resolved_by`, and it
ignores `load_skill` (a native-only host mechanism). It also does not read
`rec["exposed_tools"]`: in a routed run that list is the router's top-k exposure.

Skill attribution, in this order:
1. the skill of the first skill-bound business tool the MCP server executed (a global tool
   called before it does not decide the skill, as in the legacy native rule);
2. no business call: the skill of the tool credited by a clarification. That tool is inferred
   from the question against the acceptable tools' required fields (or "which order?"), never
   from the router's tool;
3. an escalation-only turn, or a host abstention, gives `__abstain__`;
4. only global calls gives `__global__`;
5. no action gives `__abstain__`.

Everything after the skill (first-call args/completion, NOT_ELIGIBLE and "which order?"
handling, recovery, decomposition, `args_invented`, `entity_grounded`) reuses the legacy
helpers unchanged, so the symmetric and legacy scores differ only in how the skill and the
clarification are attributed. Routing-only rows are scored by the legacy scorer (prereg-v2:
the routing primary is unchanged). `scorers.py` is imported read-only.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Any

from routing_study.eval.grounding import grounded
from routing_study.eval.scorers import (
    _SCORER_FILES,
    ESCALATE,
    _asks_for,
    _asks_which_order,
    abstain_score,
    asked_which_order,
    business_calls,
    call_args_valid,
    completion_call,
    first_call,
    first_label,
    invented_args,
    missing_required,
    recovered_call,
    refused_referred_order,
    route_scores,
    score_turn,
)
from routing_study.routers.base import ABSTAIN, GLOBAL_OPTION

SERVER_GLOBAL = "global"  # `_meta` skill of a global tool in tools/list
_SYM_FILES = ("scorers_sym.py", *_SCORER_FILES)


def scorer_sym_hash() -> str:
    """Hash of the symmetric scorer and the legacy code it reuses (scorers.py, grounding.py)."""
    h = hashlib.sha256()
    for name in _SYM_FILES:
        h.update(name.encode() + b"\0" + (Path(__file__).parent / name).read_bytes())
    return h.hexdigest()[:12]


def tool_skills(tools: Iterable[dict[str, Any]]) -> dict[str, str]:
    """tool name -> skill id from the MCP `tools/list` `_meta` (`__global__` for globals)."""
    out = {}
    for t in tools:
        skill = (t.get("_meta") or {}).get("br.routingstudy/skill")
        if skill:
            out[t["name"]] = GLOBAL_OPTION if skill == SERVER_GLOBAL else skill
    return out


def clarified_sym(
    rec: dict[str, Any],
    expected: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    turns: list[dict[str, str]] | None = None,
) -> str | None:
    """The acceptable business tool a no-call clarifying reply is credited to (first in gold
    order), or None. Same question tests as `scorers.clarified_without_call`, without the
    exposure filter and without the router's tool."""
    answer = rec.get("final_answer")
    if business_calls(rec) or not answer or "?" not in answer:
        return None

    def qualifies(tool: str) -> bool:
        props = (schemas.get(tool) or {}).get("properties") or {}
        if "order_id" in props and _asks_which_order(rec, expected, answer):
            return True
        return any(_asks_for(answer, f) for f in missing_required(tool, expected, schemas, turns))

    for t in expected["acceptable_tools"]:
        if t not in (ABSTAIN, ESCALATE) and t in schemas and qualifies(t):
            return t
    return None


def escalated_only_sym(rec: dict[str, Any]) -> bool:
    calls = business_calls(rec)
    return bool(calls) and all(c["name"] == ESCALATE for c in calls)


def behaviour_skill(
    rec: dict[str, Any], clarified: str | None, skills: dict[str, str] | None = None
) -> str:
    """Rules 1-5 of the module docstring. `skills` maps a tool to its skill (needed for rule
    2 only; a call's own recorded `skill` is used for rule 1)."""
    calls = business_calls(rec)
    for c in calls:  # rule 1
        skill = c.get("skill") or (skills or {}).get(c["name"])
        if skill and skill != GLOBAL_OPTION:
            return skill
    if not calls:
        if clarified:  # rule 2
            return (skills or {}).get(clarified, ABSTAIN)
        return ABSTAIN  # rules 3 (host abstention) and 5
    if escalated_only_sym(rec):  # rule 3
        return ABSTAIN
    return GLOBAL_OPTION  # rule 4


def score_turn_sym(
    rec: dict[str, Any],
    expected: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    turns: list[dict[str, str]] | None = None,
    read_only: Collection[str] = (),
    skills: dict[str, str] | None = None,
) -> dict[str, float | str | None]:
    """Symmetric scores of one turn. Same keys as `scorers.score_turn` minus `resolved_by`;
    `e2e_success` here IS `e2e_success_sym`. `skills`: `tool_skills(tools)`."""
    if rec["mode"] == "routing-only":
        legacy = score_turn(rec, expected, schemas, turns, read_only)
        legacy.pop("resolved_by", None)
        return legacy
    clarified = clarified_sym(rec, expected, schemas, turns)
    skill = behaviour_skill(rec, clarified, skills)
    call = completion_call(rec)
    first = first_call(rec)
    tool = clarified or (first["name"] if first else ABSTAIN)
    escalated = escalated_only_sym(rec)
    overridable = skill in (ABSTAIN, GLOBAL_OPTION)
    scores: dict[str, float | str | None] = dict(
        route_scores(skill, tool, expected, escalated=escalated, skill_overridable=overridable)
    )
    scores["abstain_correct"] = abstain_score(
        rec.get("outcome") == "abstained" or escalated, expected
    )
    scores["joint_first_label"] = route_scores(
        skill, tool, first_label(expected), escalated=escalated, skill_overridable=overridable
    )["joint_correct"]
    if clarified:
        args_ok = True
    elif call is None:
        args_ok = ABSTAIN in expected["acceptable_tools"]
    else:
        args_ok = call_args_valid(call, expected, schemas, turns)
    scores["args_valid"] = float(args_ok)
    answer = rec.get("final_answer")
    which_order = asked_which_order(call, expected, answer)
    finished = (
        call is None
        or call["status"] == "completed"
        or refused_referred_order(call, expected, turns or [], rec.get("customer"))
        or which_order
    )
    first_ok = bool(scores["tool_correct"]) and args_ok and finished
    recovered = None if first_ok else recovered_call(rec, expected, schemas, read_only, turns)
    success = bool(scores["skill_correct"]) and (first_ok or recovered is not None)
    scores["e2e_success"] = float(success)
    clar = success and first_ok and bool(clarified or which_order)
    scores["clarification_credited"] = float(clar)
    scores["recovered_credited"] = float(success and not first_ok)
    scores["first_call_success"] = float(success and first_ok and not clar)
    decisive = recovered or (None if clarified else call)
    invented = invented_args(decisive, expected, schemas, turns) if decisive else None
    scores["args_invented"] = None if invented is None else float(bool(invented))
    scores["e2e_strict"] = float(success and not invented)
    if rec.get("outcome") in ("answered", "loop_limit") and answer:
        evidence = [
            rec.get("customer"),
            *(c.get("structured") for c in business_calls(rec)),
            *(t.get("content") for t in turns or [] if t.get("role") == "user"),
        ]
        scores["entity_grounded"] = float(grounded(answer, [e for e in evidence if e])[0])
    else:
        scores["entity_grounded"] = None
    scores["grounded"] = scores["entity_grounded"]
    scores["skill_attributed"] = skill
    return scores
