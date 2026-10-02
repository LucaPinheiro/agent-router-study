"""Scores (plan §6.3) computed from one turn record (see `runner.turn_record`).

`__abstain__` stands for "no action": a routed abstention, or no business tool called.
Escalating to a human is the abstention behaviour (D4), so it counts as abstaining.

This module is THE scorer: `score_turn` (runner + `study rescore`), `simulate` and
`scripts/analysis/study_report.py` all score routing decisions through `routing_scores` /
`route_scores`, so the out-of-scope mapping cannot drift between consumers (review H1).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from routing_study.eval.grounding import grounded
from routing_study.routers.base import ABSTAIN, GLOBAL_OPTION

LOAD_SKILL = "load_skill"
ESCALATE = "escalate_to_human"
_ORDER_ID = re.compile(r"\bO\d{4}\b", re.IGNORECASE)
_CEP = re.compile(r"\b(\d{5})-?(\d{3})\b")
_ABBREV = {"r": "rua", "av": "avenida", "al": "alameda", "tv": "travessa", "rod": "rodovia"}
QUERY_MIN_OVERLAP = 0.5
_SCORER_FILES = ("scorers.py", "grounding.py")


REFUSED = "refused"  # host refusal (tool not exposed / skill not loaded): never executed


def scorer_hash() -> str:
    """Hash of the scoring code (this module + grounding): recorded in result rows and in
    the rescore provenance header, so scores computed by different scorer versions never mix."""
    h = hashlib.sha256()
    for name in _SCORER_FILES:
        h.update(name.encode() + b"\0" + (Path(__file__).parent / name).read_bytes())
    return h.hexdigest()[:12]


def tool_index(tools: Iterable[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], frozenset[str]]:
    """(name -> inputSchema, read-only tool names) from MCP `tools/list` entries; read-only
    comes from the `readOnlyHint` annotation, never from the tool name (review L3)."""
    tools = list(tools)
    schemas = {t["name"]: t.get("inputSchema") or {} for t in tools}
    read_only = frozenset(
        t["name"] for t in tools if (t.get("annotations") or {}).get("readOnlyHint")
    )
    return schemas, read_only


def business_calls(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """Tool calls the MCP server executed (no load_skill, no host-refused calls)."""
    return [
        c for c in rec.get("calls", []) if c["name"] != LOAD_SKILL and c.get("status") != REFUSED
    ]


def first_call(rec: dict[str, Any]) -> dict[str, Any] | None:
    calls = business_calls(rec)
    return calls[0] if calls else None


def completion_call(rec: dict[str, Any]) -> dict[str, Any] | None:
    """The call that decides args/completion of the first business tool: its successful
    retry when it failed with a recoverable error (e.g. "which order?")."""
    calls = business_calls(rec)
    if not calls:
        return None
    current = calls[0]
    for c in calls[1:]:
        if c["name"] != current["name"]:
            continue
        err = current.get("structured") or {}
        if current.get("status") == "completed" or not err.get("recoverable"):
            break
        current = c
    return current


def chosen_skill(rec: dict[str, Any]) -> str:
    if not rec["native"]:
        skill = rec.get("skill") or {}
        return ABSTAIN if skill.get("abstained") or not skill.get("choice") else skill["choice"]
    # native: the first skill it loaded or whose tool it called; a global tool called before
    # that (e.g. a help-center search, then load_skill) does not decide the skill: __global__
    # only when no skill was ever loaded (F5)
    used_global = False
    for c in rec.get("calls", []):
        if c["name"] == LOAD_SKILL and c["args"].get("skill"):
            return c["args"]["skill"]
        if c["name"] != LOAD_SKILL and c.get("status") != REFUSED:
            skill = c.get("skill")
            if skill and skill != GLOBAL_OPTION:
                return skill
            used_global = True
    return GLOBAL_OPTION if used_global else ABSTAIN


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


def _tokens(text: Any) -> list[str]:
    """Accent-free, casefolded word tokens; street abbreviations expanded (R. -> rua)."""
    plain = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return [_ABBREV.get(t, t) for t in re.findall(r"[0-9a-z]+", plain.casefold())]


def _address_match(gold: str, args: dict[str, Any]) -> bool:
    """Free-text gold address vs the tool's address fields: street and number words appear
    in the gold address, and the postal code matches when the gold has a CEP."""
    words = set(_tokens(gold))
    street, number = _tokens(args.get("street")), _tokens(args.get("number"))
    if not street or not number or not set(street + number) <= words:
        return False
    cep = _CEP.search(gold)
    return cep is None or re.sub(r"\D", "", str(args.get("postal_code") or "")) == "".join(
        cep.groups()
    )


def _query_match(gold: str, actual: Any) -> bool:
    """Free-text query: at least half of the gold content words appear in the call."""
    want = {t for t in _tokens(gold) if len(t) > 2}
    return not want or len(want & set(_tokens(actual))) / len(want) >= QUERY_MIN_OVERLAP


def _arg_match(key: str, expected: Any, args: dict[str, Any], params: dict[str, Any]) -> bool:
    """Gold keys that are not parameters of the called tool are not compared, except
    `address`, which maps onto the address fields."""
    if key == "address" and {"street", "number"} <= params.keys():
        return _address_match(str(expected), args)
    if key not in params:
        return True
    if key == "query":
        return _query_match(str(expected), args.get(key))
    return _match(expected, args.get(key))


def user_order_ids(turns: list[dict[str, str]] | None) -> set[str]:
    """Order ids the customer wrote (normalized like the mock server)."""
    out: set[str] = set()
    for t in turns or []:
        if t.get("role") == "user":
            out |= {o for m in _ORDER_ID.findall(t.get("content") or "") if (o := _order_id(m))}
    return out


def call_args_valid(
    call: dict[str, Any],
    expected: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    turns: list[dict[str, str]] | None = None,
) -> bool:
    """Schema-valid, the gold args match, and an `order_id` the call passed is one the
    customer wrote when they wrote any (F5: enforced even when the gold omits order_id)."""
    schema = schemas.get(call["name"])
    if schema is None or any(True for _ in Draft202012Validator(schema).iter_errors(call["args"])):
        return False
    params = schema.get("properties") or {}
    written = user_order_ids(turns)
    called = _order_id(call["args"].get("order_id"))
    if written and "order_id" in params and called is not None and called not in written:
        return False
    return all(
        _arg_match(k, v, call["args"], params) for k, v in (expected.get("args") or {}).items()
    )


def args_valid(
    rec: dict[str, Any],
    expected: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    turns: list[dict[str, str]] | None = None,
) -> bool:
    call = completion_call(rec)
    if call is None:
        return ABSTAIN in expected["acceptable_tools"]
    return call_args_valid(call, expected, schemas, turns)


# ---------------------------------------------------------------- clarification / invention

# Required params that are not customer facts: the escalation note is written for the human
# agent and the help-center query paraphrases the question (compared to the gold by overlap).
_NOT_FACTS = {(ESCALATE, "reason"), ("search_help_center", "query")}
_ADDRESS_FIELDS = {"street", "number", "complement", "neighborhood", "city", "state", "postal_code"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
# a date the customer gave, in any form the executor could turn into AAAA-MM-DD
_DATE_HINT = re.compile(
    r"\b(\d{1,2}/\d{1,2}|\d{4}-\d{2}-\d{2}|dia \d{1,2}|amanha|hoje|semana que vem|"
    r"proxima semana|segunda|terca|quarta|quinta|sexta|sabado|domingo|janeiro|fevereiro|"
    r"marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b"
)
# the customer already gave a free-text required field (accent-free, casefolded user turns):
# lexical cues per field, documented in docs/metrics.md (F5). A field whose cue matches is not
# missing, so asking for it earns no clarification credit.
_ADDRESS_CUE = re.compile(r"\b(rua|r|avenida|av|alameda|travessa|rodovia|cep|\d{5}-?\d{3})\b")
_PROVIDED = {
    "defect_description": re.compile(
        r"\b(defeit\w*|quebr\w*|parou|para de|nao (liga|funciona|carrega|acende|conecta|"
        r"fecha|abre)|rasg\w*|manch\w*|trinc\w*|riscad\w*|amassad\w*|vaz\w*|estragad\w*|"
        r"falh\w*|descostur\w*|desligando|esquent\w*|chiado|barulho)"
    ),
    "reason": re.compile(
        r"\b(porque|pois|motivo|por causa|desisti\w*|arrepend\w*|nao (quero|preciso|gostei|"
        r"serviu|coube|reconheco)|errad\w*|atras\w*|cobrad\w* (duas|2) vezes|duplicad\w*)"
    ),
    "new_variant": re.compile(
        r"\b(tamanho|numero|numeracao|cor|modelo|voltagem|110|220|pp|p|m|g|gg|xg|\d{2}|"
        r"azul|preto|preta|branco|branca|vermelh\w*|verde|rosa|cinza|amarel\w*|bege|marrom)\b"
    ),
    **dict.fromkeys(_ADDRESS_FIELDS, _ADDRESS_CUE),
}
# words of a reply that asks the customer for a required field (accent-free, casefolded)
_ASKS_FOR = {
    "new_date": ("data", "dia", "quando"),
    "new_variant": ("tamanho", "cor", "variac", "numera", "modelo", "variante"),
    "defect_description": ("defeito", "problema", "aconteceu", "descrev"),
    "reason": ("motivo", "por que", "porque", "razao", "aconteceu"),
    **{f: ("endereco", "cep", "rua", "bairro", "cidade", "numero") for f in _ADDRESS_FIELDS},
}


def _plain(text: Any) -> str:
    return (
        unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().casefold()
    )


def _user_text(turns: list[dict[str, str]] | None) -> str:
    return _plain(" ".join(t.get("content") or "" for t in turns or [] if t.get("role") == "user"))


def _said_by_user(value: Any, user_text: str) -> bool:
    """The customer's turns support `value`: a date hint for an ISO date, else at least half
    of its content words (numbers included)."""
    if _ISO_DATE.match(str(value)):
        return bool(_DATE_HINT.search(user_text))
    want = {t for t in _tokens(value) if len(t) > 2 or t.isdigit()}
    return not want or len(want & set(_tokens(user_text))) / len(want) >= QUERY_MIN_OVERLAP


def _gold_covers(field: str, expected: dict[str, Any]) -> bool:
    gold = expected.get("args") or {}
    return field in gold or (field in _ADDRESS_FIELDS and "address" in gold)


def invented_args(
    call: dict[str, Any],
    expected: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    turns: list[dict[str, str]] | None,
) -> list[str]:
    """Required free-text args of `call` that neither the gold args nor the customer's turns
    support: the executor made them up (review H3). Enum params (a category the executor
    picks) and non-fact params (`_NOT_FACTS`) are never flagged."""
    schema = schemas.get(call["name"]) or {}
    props = schema.get("properties") or {}
    user = _user_text(turns)
    out = []
    for f in schema.get("required") or []:
        value = call["args"].get(f)
        if (
            (call["name"], f) in _NOT_FACTS
            or _gold_covers(f, expected)
            or value in (None, "")
            or "enum" in (props.get(f) or {})
        ):
            continue
        if not _said_by_user(value, user):
            out.append(f)
    return out


def missing_required(
    tool: str,
    expected: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    turns: list[dict[str, str]] | None,
) -> list[str]:
    """Required fields of `tool` the conversation does not provide: asking for them is a
    correct clarification (review H3). An enum field counts as provided when the customer's
    words match one of its values."""
    schema = schemas.get(tool) or {}
    props = schema.get("properties") or {}
    user = _user_text(turns)
    out = []
    for f in schema.get("required") or []:
        if (tool, f) in _NOT_FACTS or _gold_covers(f, expected):
            continue
        enum = (props.get(f) or {}).get("enum")
        if enum and any(_said_by_user(str(v).replace("_", " "), user) for v in enum):
            continue
        if not enum and f == "new_date" and _DATE_HINT.search(user):
            continue
        if not enum and f in _PROVIDED and _PROVIDED[f].search(user):
            continue
        out.append(f)
    return out


_QUESTION = re.compile(r"[^.!?\n]*\?")
# the reply says it already did the action: then it is not a clarifying question
_SUCCESS_CLAIM = re.compile(
    r"\b(pronto|sucesso|conclui\w*|realizad[oa]s?|efetuad[oa]s?|ja (cancelei|abri|registrei|"
    r"solicitei|alterei|troquei|gerei|reagendei|atualizei|fiz)|foi (cancelad|registrad|abert|"
    r"alterad|reagendad|solicitad|criad|gerad|emitid|atualizad|contestad)\w*)"
)


def questions(answer: str) -> list[str]:
    """The question sentences of a reply (accent-free, casefolded)."""
    return _QUESTION.findall(_plain(answer))


def _asks_for(answer: str, field: str) -> bool:
    """A question sentence of the reply names the field (word-start match): a keyword
    outside the questions (e.g. "Entendi o problema.") does not count (F5)."""
    words = _ASKS_FOR.get(field, (field.replace("_", " "),))
    return any(re.search(r"\b" + re.escape(w), q) for q in questions(answer) for w in words)


def claims_success(answer: str) -> bool:
    return bool(_SUCCESS_CLAIM.search(_plain(answer)))


def offers_order_choice(answer: str, ids: Iterable[str]) -> bool:
    """A which-order clarification: a question, at least two of the ids offered, and no
    claim that an action was already done (F5)."""
    text = answer.casefold()
    offered = {str(i).casefold() for i in ids if str(i).casefold() in text}
    return bool(questions(answer)) and len(offered) >= 2 and not claims_success(answer)


def _asks_which_order(rec: dict[str, Any], expected: dict[str, Any], answer: str) -> bool:
    if "order_id" in (expected.get("args") or {}):
        return False
    owned = [str(o.get("order_id")) for o in (rec.get("customer") or {}).get("orders") or []]
    return len(owned) >= 2 and offers_order_choice(answer, owned)


def clarified_without_call(
    rec: dict[str, Any],
    expected: dict[str, Any],
    schemas: dict[str, dict[str, Any]] | None = None,
    turns: list[dict[str, str]] | None = None,
) -> str | None:
    """No business tool ran and the reply is a question that a correct next step needed:
    "which order?" (the user named none, the customer has several) for a tool that takes
    `order_id`, or a missing required field of the tool (H3). Only an acceptable, exposed,
    business tool is credited (never escalation / abstention, M1), and in routed runs only
    the router's own tool choice (finding 1). Returns that tool, else None."""
    answer = rec.get("final_answer")
    if business_calls(rec) or not answer or "?" not in answer:
        return None
    schemas = schemas or {}
    exposed = set(rec.get("exposed_tools") or [])

    def qualifies(tool: str) -> bool:
        props = (schemas.get(tool) or {}).get("properties") or {}
        if "order_id" in props and _asks_which_order(rec, expected, answer):
            return True
        return any(_asks_for(answer, f) for f in missing_required(tool, expected, schemas, turns))

    ok = [
        t
        for t in expected["acceptable_tools"]
        if t in exposed and t not in (ABSTAIN, ESCALATE) and qualifies(t)
    ]
    router_tool = (rec.get("tool") or {}).get("choice")
    if not rec["native"] and router_tool:
        return router_tool if router_tool in ok else None
    return ok[0] if ok else None


def recovered_call(
    rec: dict[str, Any],
    expected: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    read_only: Collection[str] = (),
    turns: list[dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    """A later business call to an acceptable tool that completed with valid args: the
    customer's goal was reached even if the first attempt was another tool. Only when no
    earlier call completed an action (a tool without `readOnlyHint`): an action on the wrong
    target is never rescued."""
    calls = business_calls(rec)
    for i, c in enumerate(calls[1:], start=1):
        if any(p.get("status") == "completed" and p["name"] not in read_only for p in calls[:i]):
            return None
        if (
            c["name"] in expected["acceptable_tools"]
            and c.get("status") == "completed"
            and call_args_valid(c, expected, schemas, turns)
        ):
            return c
    return None


def expects_abstention(expected: dict[str, Any]) -> bool:
    """No business action is acceptable: only abstention / escalation are listed."""
    return set(expected["acceptable_tools"]) <= {ABSTAIN, ESCALATE}


def allows_abstention(expected: dict[str, Any]) -> bool:
    """Abstaining or escalating is an acceptable answer (escalation is the abstention, D4)."""
    return bool(set(expected["acceptable_tools"]) & {ABSTAIN, ESCALATE})


def abstain_score(abstained: bool, expected: dict[str, Any]) -> float:
    return float(allows_abstention(expected) if abstained else not expects_abstention(expected))


def escalated_only(rec: dict[str, Any]) -> bool:
    """Escalating to a human was the only business action of the turn."""
    if rec["mode"] == "routing-only":
        return chosen_tool(rec) == ESCALATE
    calls = business_calls(rec)
    return bool(calls) and all(c["name"] == ESCALATE for c in calls)


def _order_id(raw: Any) -> str | None:
    """Normalized like the mock server's `resolve_order` (case-insensitive, 2 -> O0002)."""
    if not isinstance(raw, str | int) or not str(raw).strip():
        return None
    oid = str(raw).strip().upper()
    return f"O{int(oid):04d}" if oid.isdigit() else oid


def refused_referred_order(
    call: dict[str, Any],
    expected: dict[str, Any],
    turns: list[dict[str, str]],
    customer: dict[str, Any] | None,
) -> bool:
    """A NOT_ELIGIBLE refusal finishes the task only on the order the user meant: the gold
    order, an order id the user wrote, or the customer's only order."""
    if (call.get("structured") or {}).get("code") != "NOT_ELIGIBLE":
        return False
    owned = [o.get("order_id") for o in (customer or {}).get("orders") or []]
    called = _order_id(call["args"].get("order_id"))
    if len(owned) == 1 and called in (None, _order_id(owned[0])):
        return True
    referred = {_order_id((expected.get("args") or {}).get("order_id"))}
    for t in turns:
        if t.get("role") == "user":
            referred |= {_order_id(m) for m in _ORDER_ID.findall(t.get("content") or "")}
    return called is not None and called in referred


def asked_which_order(
    call: dict[str, Any] | None, expected: dict[str, Any], answer: str | None
) -> bool:
    """Correct clarification: the user named no order, the customer has several, the tool
    answered a recoverable VALIDATION_ERROR listing them and the reply asks a question
    offering at least two of them back, without claiming an action was done (F5)."""
    if call is None or "order_id" in (expected.get("args") or {}) or not answer:
        return False
    err = call.get("structured") or {}
    options = (err.get("details") or {}).get("options") or []
    if not (err.get("code") == "VALIDATION_ERROR" and err.get("recoverable") and len(options) > 1):
        return False
    return offers_order_choice(answer, options)


# ---------------------------------------------------------------- shared routing scores


def routing_failure(steps: Iterable[dict[str, Any]], accepted: bool) -> str | None:
    """A routing stage failed (an error row, never a scored abstention; review M4) when no
    consulted step accepted and one of them raised (`usage.error`) or returned an unparseable
    reply (`usage.parse_fail`). A failure a later step recovered from is not an error
    (finding 2)."""
    if accepted:
        return None
    for st in steps:
        usage = st.get("usage") or {}
        if usage.get("error"):
            return f"{st.get('strategy')}: {usage['error']}"
        if usage.get("parse_fail"):
            return f"{st.get('strategy')}: parse_fail"
    return None


def route_scores(
    skill: str,
    tool: str,
    expected: dict[str, Any],
    *,
    escalated: bool,
    skill_overridable: bool,
) -> dict[str, float]:
    """Skill / tool / joint correctness, shared by every consumer (H1). An out-of-scope gold
    (`__abstain__`) is also satisfied by escalating as the only action (D4): the tool counts as
    `__abstain__`, and so does the skill when it was not a business-skill decision (native
    agent, or the router abstained / chose `__global__`; finding 7)."""
    if escalated:
        if skill_overridable and ABSTAIN in expected["acceptable_skills"]:
            skill = ABSTAIN
        if ABSTAIN in expected["acceptable_tools"]:
            tool = ABSTAIN
    skill_ok = skill in expected["acceptable_skills"]
    tool_ok = tool in expected["acceptable_tools"]
    return {
        "skill_correct": float(skill_ok),
        "tool_correct": float(tool_ok),
        "joint_correct": float(skill_ok and tool_ok),
    }


def routing_scores(
    skill: str | None, tool: str | None, expected: dict[str, Any]
) -> dict[str, float]:
    """Scores of a routing-only decision pair: a recorded run, one shadow strategy or a
    simulated cascade. `None` = abstained; an abstained skill stage never reaches the tool."""
    skill = skill or ABSTAIN
    tool = ABSTAIN if skill == ABSTAIN else (tool or ABSTAIN)
    s = route_scores(
        skill,
        tool,
        expected,
        escalated=tool == ESCALATE,
        skill_overridable=skill in (ABSTAIN, GLOBAL_OPTION),
    )
    return s | {"abstain_correct": abstain_score(tool in (ABSTAIN, ESCALATE), expected)}


def skill_can_be_correct(skill: str | None, expected: dict[str, Any]) -> bool:
    """Whether a skill decision can still be scored correct once its tool stage is known:
    an acceptable skill, or `__global__` on an out-of-scope gold (escalation maps it)."""
    skill = skill or ABSTAIN
    return skill in expected["acceptable_skills"] or (
        skill == GLOBAL_OPTION and ABSTAIN in expected["acceptable_skills"]
    )


# ---------------------------------------------------------------- turn scores


E2E_ONLY = (
    "args_valid",
    "args_invented",
    "e2e_success",
    "e2e_strict",
    "first_call_success",
    "clarification_credited",
    "recovered_credited",
    "entity_grounded",
    "grounded",
)


def first_label(expected: dict[str, Any]) -> dict[str, Any]:
    """The gold restricted to its FIRST acceptable skill and tool (strict sensitivity)."""
    return expected | {
        "acceptable_skills": expected["acceptable_skills"][:1],
        "acceptable_tools": expected["acceptable_tools"][:1],
    }


def first_label_joint(
    skill: str, tool: str, expected: dict[str, Any], rec: dict[str, Any], escalated: bool = False
) -> float:
    """Joint correctness against the first-listed labels only (methodology M4 sensitivity);
    the out-of-scope escalation mapping is the same as the primary score's."""
    strict = first_label(expected)
    if rec["mode"] == "routing-only":
        return routing_scores(skill, tool, strict)["joint_correct"]
    return route_scores(
        skill,
        tool,
        strict,
        escalated=escalated,
        skill_overridable=rec["native"] or skill in (ABSTAIN, GLOBAL_OPTION),
    )["joint_correct"]


def score_turn(
    rec: dict[str, Any],
    expected: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    turns: list[dict[str, str]] | None = None,
    read_only: Collection[str] = (),
) -> dict[str, float | str | None]:
    """name -> value (None = not applicable for this turn/mode). `turns` is the case
    conversation (user order ids make a NOT_ELIGIBLE refusal count; user words support
    arguments); `read_only` the tools annotated readOnlyHint (see `tool_index`).

    `tool_correct` is the router's top-1 in routing-only mode and the executor's first call
    (or clarification credit) in e2e: report them as different columns (L1)."""
    skill, tool = chosen_skill(rec), chosen_tool(rec)
    resolved_by = (
        "native" if rec["native"] else (rec.get("skill") or {}).get("resolved_by") or "abstained"
    )
    if rec["mode"] == "routing-only":
        return (
            routing_scores(skill, tool, expected)
            | {"joint_first_label": first_label_joint(skill, tool, expected, rec)}
            | {"resolved_by": resolved_by}
            | dict.fromkeys(E2E_ONLY)
        )
    clarified = clarified_without_call(rec, expected, schemas, turns)
    if clarified:  # asked the question the next step needed; credit the tool it was for
        tool = clarified
    escalated = escalated_only(rec)
    scores: dict[str, float | str | None] = dict(
        route_scores(
            skill,
            tool,
            expected,
            escalated=escalated,
            skill_overridable=rec["native"] or skill in (ABSTAIN, GLOBAL_OPTION),
        )
    )
    # M5: only a host abstention or an escalation-only turn is an abstention in e2e; a reply
    # without a tool call (e.g. a clarifying question) is not
    scores["abstain_correct"] = abstain_score(
        rec.get("outcome") == "abstained" or escalated, expected
    )
    scores["joint_first_label"] = first_label_joint(skill, tool, expected, rec, escalated)
    scores["resolved_by"] = resolved_by
    args_ok = True if clarified else args_valid(rec, expected, schemas, turns)
    call = completion_call(rec)
    scores["args_valid"] = float(args_ok)
    answer = rec.get("final_answer")
    # The server ran the right tool: completed, a business refusal that depends on the mock
    # fixture's order state (NOT_ELIGIBLE) on the order the user meant, or a correct
    # "which order?" clarification.
    which_order = asked_which_order(call, expected, answer)
    finished = (
        call is None
        or call["status"] == "completed"
        or refused_referred_order(call, expected, turns or [], rec.get("customer"))
        or which_order
    )
    # tool_correct stays strict (first call); e2e_success is the customer's outcome, so a
    # later completed call to an acceptable tool with valid args also counts.
    first_ok = bool(scores["tool_correct"]) and args_ok and finished
    recovered = None if first_ok else recovered_call(rec, expected, schemas, read_only, turns)
    success = bool(scores["skill_correct"]) and (first_ok or recovered is not None)
    scores["e2e_success"] = float(success)
    # F6 decomposition (the three parts sum to e2e_success): the first business call did it;
    # a clarifying question was credited (no call, or "which order?" after the tool asked);
    # a later acceptable call recovered the goal
    clar = success and first_ok and bool(clarified or which_order)
    scores["clarification_credited"] = float(clar)
    scores["recovered_credited"] = float(success and not first_ok)
    scores["first_call_success"] = float(success and first_ok and not clar)
    # H3: the call that decided the outcome filled a required fact nobody gave
    decisive = recovered or (None if clarified else call)
    invented = invented_args(decisive, expected, schemas, turns) if decisive else None
    scores["args_invented"] = None if invented is None else float(bool(invented))
    scores["e2e_strict"] = float(success and not invented)
    if rec.get("outcome") in ("answered", "loop_limit") and answer:  # incl. wrap-up answers
        # evidence: the profile, tool results and what the customer wrote (finding 10)
        evidence = [
            rec.get("customer"),
            *(c.get("structured") for c in business_calls(rec)),
            *(t.get("content") for t in turns or [] if t.get("role") == "user"),
        ]
        scores["entity_grounded"] = float(grounded(answer, [e for e in evidence if e])[0])
    else:
        scores["entity_grounded"] = None
    scores["grounded"] = scores["entity_grounded"]  # alias of the pre-F6 name (old rows)
    return scores
