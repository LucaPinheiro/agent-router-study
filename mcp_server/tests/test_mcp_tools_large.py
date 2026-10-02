"""Large profile (CATALOG_PROFILE=large): the 44 new tools, the overlay of the 18 originals, the
10 skills and the confusable-group rules. The shared contract tests (catalog shape, resources,
HAPPY/ERRORS of the originals, cross-tool consistency) run on both profiles via `client`."""

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml
from fastmcp import Client
from mcp_fixtures import SERVERS, meta
from mcp_server.core import RDNS, REGISTRY
from mcp_server.large.data import DB_L
from mcp_server.large.overrides import EXAMPLES, POINTERS, REPLACE
from mcp_server.large.probes import entity_probes
from mcp_server.server import SKILL_IDS, SKILL_IDS_LARGE, profile_from_env, skill_path
from mcp_server.tools_large import REGISTRY_LARGE
from test_mcp_tools import EXPECTED_TOOLS_LARGE

DATA = Path(__file__).resolve().parents[2] / "data"
PHASE1_SPLITS = ("dataset_dev.jsonl", "dataset_test.jsonl", "dataset_test_v2.jsonl")

# plan §1: the 12 designed confusable groups; each must have a disambiguation rule (one
# bullet naming every tool of the group) in some SKILL.md
GROUPS = {
    "G1 cobrança errada": ("dispute_charge", "contest_card_transaction", "open_seller_mediation"),
    "G2 2ª via": ("generate_boleto_second_copy", "generate_card_bill_copy", "get_card_bill"),
    "G3 dinheiro não caiu": ("get_refund_status", "get_cashback_status", "claim_missing_points"),
    "G4 cancelar": ("cancel_order", "cancel_subscription", "cancel_service_order"),
    "G5 mudar a data": (
        "reschedule_delivery",
        "change_subscription_date",
        "reschedule_technical_visit",
    ),
    "G6 onde está": ("track_shipment", "track_seller_shipment"),
    "G7 defeito": ("open_warranty_claim", "request_technical_visit", "check_extended_warranty"),
    "G8 mudar meus dados": (
        "update_delivery_address",
        "update_billing_data",
        "update_contact_info",
    ),
    "G9 baixou o preço": ("request_price_protection", "request_refund"),
    "G10 devolver de parceiro/PJ": (
        "create_return_request",
        "issue_return_invoice",
        "open_seller_mediation",
    ),
    "G11 comprovante": ("get_payment_status", "get_purchase_receipt", "get_invoice"),
    "G12 cupom/vale": ("validate_coupon", "report_coupon_not_applied", "redeem_gift_card"),
}


@pytest.fixture
async def large() -> Any:
    async with Client(SERVERS["large"]) as c:
        yield c


@pytest.fixture
async def small() -> Any:
    async with Client(SERVERS["small"]) as c:
        yield c


async def _call(client: Client, tool: str, customer: str | None, args: dict[str, Any]) -> Any:
    return await client.call_tool(tool, args, meta=meta(customer), raise_on_error=False)


def _os(order_id: str) -> str:
    return next(s["id"] for s in DB_L["service_orders"] if s["order_id"] == order_id)


def _tx(customer: str, contested: bool) -> str:
    card = next(c for c in DB_L["store_cards"] if c["customer_id"] == customer)
    return next(t["id"] for t in card["bill"]["transactions"] if t["contested"] is contested)


# ------------------------------------------------------------------ catalog


async def test_large_catalog_counts_and_new_tool_metadata(large: Client) -> None:
    tools = {t.name: t for t in await large.list_tools()}
    assert len(tools) == 62 and len(REGISTRY_LARGE) == 44
    new = {t.name for t in REGISTRY_LARGE}
    assert new == set().union(*EXPECTED_TOOLS_LARGE.values()) - {t.name for t in REGISTRY}
    for name in new:
        m = tools[name].meta
        assert len(m[f"{RDNS}/examples"]) == 4, name  # plan T3.1: 4 `_meta` examples
        assert len(set(m[f"{RDNS}/examples"])) == 4 and m[f"{RDNS}/keywords"]
        # every DON'T USE FOR pointer names a tool of the large catalog
        avoid = next(ln for ln in tools[name].description.split("\n") if "DON'T USE FOR" in ln)
        for target in re.findall(r"\(use ([^)]*)\)", avoid):
            names = [t for t in re.findall(r"[a-z_]+", target) if "_" in t]
            assert names and all(t in tools for t in names), (name, target)


async def test_overlay_only_appends_pointers_in_large(large: Client, small: Client) -> None:
    small_tools = {t.name: t for t in await small.list_tools()}
    large_tools = {t.name: t for t in await large.list_tools()}
    assert set(POINTERS) | set(REPLACE) <= set(small_tools)
    for name, t in small_tools.items():
        expected = t.description
        for old, new in REPLACE.get(name, []):
            expected = expected.replace(old, new)
        got = large_tools[name].description
        if name in POINTERS:
            assert got.replace(f"; {POINTERS[name]}.", ".", 1) == expected, name
            for target in re.findall(r"\(use ([a-z_]+)\)", POINTERS[name]):
                assert target in large_tools, (name, target)
        else:
            assert got == expected, name
        # schemas, annotations and the other `_meta` keys are the originals'
        assert large_tools[name].input_schema == t.input_schema
        assert large_tools[name].output_schema == t.output_schema
        assert large_tools[name].annotations == t.annotations
        examples = EXAMPLES.get(name, t.meta[f"{RDNS}/examples"])
        assert large_tools[name].meta == {**t.meta, f"{RDNS}/examples": examples}
    # the small registry objects themselves are untouched
    assert all("track_seller_shipment" not in (t.description or "") for t in REGISTRY)


def test_profile_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CATALOG_PROFILE", raising=False)
    assert profile_from_env() == "small"
    monkeypatch.setenv("CATALOG_PROFILE", "LARGE")
    assert profile_from_env() == "large"
    monkeypatch.setenv("CATALOG_PROFILE", "medium")
    with pytest.raises(ValueError, match="CATALOG_PROFILE"):
        profile_from_env()


async def test_small_server_has_no_large_content(small: Client) -> None:
    names = {t.name for t in await small.list_tools()}
    assert names.isdisjoint(t.name for t in REGISTRY_LARGE)
    uris = {str(r.uri) for r in await small.list_resources()}
    assert not any("assinaturas" in u for u in uris)


# ------------------------------------------------------------------ skills


def _skill(skill_id: str) -> tuple[dict[str, Any], str]:
    _, front, body = skill_path(skill_id).read_text(encoding="utf-8").split("---", 2)
    return yaml.safe_load(front), body


def test_original_playbooks_are_served_verbatim() -> None:
    for skill_id in SKILL_IDS:
        assert skill_path(skill_id).parent.parent.name == "skills"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_every_confusable_group_has_a_skill_rule(group: str) -> None:
    tools = GROUPS[group]
    hits = []
    for skill_id in SKILL_IDS_LARGE:
        _, body = _skill(skill_id)
        rules = body.split("## Heurística de desambiguação", 1)[1].split("\n## ", 1)[0]
        hits += [
            skill_id
            for line in rules.splitlines()
            if line.startswith("- ") and all(t in line for t in tools)
        ]
    assert hits, f"{group}: no disambiguation bullet names all of {tools}"


def test_new_skills_frontmatter() -> None:
    for skill_id in SKILL_IDS_LARGE[3:]:
        fm, body = _skill(skill_id)
        assert fm["name"] == skill_id and fm["description"]
        assert 3 <= len(fm["examples"]) <= 5
        assert set(fm["allowed-tools"]) == EXPECTED_TOOLS_LARGE[skill_id]
        for section in (
            "## Cenários e tool certa",
            "## Heurística de desambiguação",
            "## Sequências típicas",
            "## Anti-padrões",
        ):
            assert section in body, (skill_id, section)


# ------------------------------------------------------------------ every tool completes


async def test_every_new_tool_completes_on_some_mock_entity(large: Client) -> None:
    schemas = {t.name: t.output_schema for t in await large.list_tools()}
    completed: dict[str, int] = {t.name: 0 for t in REGISTRY_LARGE}
    for _, _, cid, _, calls in entity_probes(DB_L):
        for _, tool, args in calls:
            r = await _call(large, tool, cid, args)
            jsonschema.validate(r.structured_content, schemas[tool])
            assert r.content[0].text
            if not r.is_error:
                completed[tool] += 1
    assert all(completed.values()), [t for t, n in completed.items() if not n]


async def test_mock_db_notes_are_current() -> None:
    notes = (Path(__file__).parents[1] / "MOCK_DB_NOTES_LARGE.md").read_text(encoding="utf-8")
    for kind, eid, cid, arch, _ in entity_probes(DB_L):
        assert f"| {kind} | {eid} | {cid} | {arch} |" in notes


# ------------------------------------------------------------------ business errors

ERRORS_L: dict[str, list[tuple[str | None, dict[str, Any], str, str | None]]] = {
    # tool: [(customer, args, code, suggested_tool)]
    "schedule_installation": [
        ("C001", {"order_id": "O0002", "date": "2026-10-03"}, "NOT_ELIGIBLE", None),
        (
            "C010",
            {"order_id": "O0029", "date": "2026-10-03"},
            "NOT_ELIGIBLE",
            "get_service_order_status",
        ),
        ("C003", {"order_id": "O0007", "date": "2020-01-01"}, "VALIDATION_ERROR", None),
    ],
    "request_technical_visit": [
        (
            "C005",
            {"order_id": "O0014", "date": "2026-10-03", "problem_description": "x"},
            "NOT_ELIGIBLE",
            "check_extended_warranty",
        ),
        (
            "C016",
            {"order_id": "O0047", "date": "2026-10-03", "problem_description": "x"},
            "NOT_ELIGIBLE",
            "open_warranty_claim",
        ),
    ],
    "reschedule_technical_visit": [
        (
            "C003",
            {"service_order_id": _os("O0007"), "new_date": "2026-10-03"},
            "NOT_ELIGIBLE",
            "get_service_order_status",
        ),
    ],
    "get_service_order_status": [("C001", {}, "NOT_FOUND", None)],
    "cancel_service_order": [
        ("C017", {"service_order_id": _os("O0049")}, "NOT_ELIGIBLE", "get_service_order_status"),
    ],
    "check_extended_warranty": [
        ("C001", {"order_id": "O0003"}, "NOT_ELIGIBLE", "get_order_status"),
    ],
    "get_seller_info": [("C001", {"order_id": "O0001"}, "NOT_ELIGIBLE", "track_shipment")],
    "contact_seller": [
        ("C001", {"order_id": "O0003", "message": "oi?"}, "NOT_ELIGIBLE", "get_order_status"),
    ],
    "track_seller_shipment": [("C001", {"order_id": "O0001"}, "NOT_ELIGIBLE", "track_shipment")],
    "open_seller_mediation": [
        (
            "C012",
            {"order_id": "O0035", "reason": "sem_resposta"},
            "NOT_ELIGIBLE",
            "check_protocol_status",
        ),
    ],
    "report_seller_issue": [
        (
            "C001",
            {"order_id": "O0001", "issue_type": "outro", "details": "xyz"},
            "NOT_ELIGIBLE",
            "track_shipment",
        ),
    ],
    "rate_seller": [
        ("C007", {"order_id": "O0019", "rating": 3}, "NOT_ELIGIBLE", None),
        ("C009", {"order_id": "O0026", "rating": 3}, "NOT_ELIGIBLE", "track_seller_shipment"),
    ],
    "get_subscription": [
        ("C002", {}, "NOT_FOUND", None),
        ("C005", {}, "VALIDATION_ERROR", None),
    ],
    "pause_subscription": [("C012", {}, "NOT_ELIGIBLE", "get_subscription")],
    "cancel_subscription": [("C008", {}, "NOT_ELIGIBLE", "get_subscription")],
    "change_subscription_date": [("C001", {"new_date": "2020-01-01"}, "VALIDATION_ERROR", None)],
    "change_subscription_items": [
        ("C001", {"sku": "XYZ-1", "quantity": 1}, "VALIDATION_ERROR", None),
        ("C001", {"sku": "CAP-CAFE-50", "quantity": 0}, "VALIDATION_ERROR", None),
    ],
    "update_subscription_payment": [
        ("C001", {"method": "credit_card", "card_last4": "0000"}, "VALIDATION_ERROR", None),
        ("C003", {"method": "cartao_loja"}, "NOT_ELIGIBLE", None),
    ],
    "get_invoice": [("C001", {"order_id": "O0003"}, "NOT_ELIGIBLE", "get_order_status")],
    "resend_invoice": [("C002", {"order_id": "O0005"}, "NOT_ELIGIBLE", "get_order_status")],
    "request_invoice_correction": [
        (
            "C001",
            {"order_id": "O0001", "field": "inscricao_estadual", "correct_value": "123"},
            "VALIDATION_ERROR",
            None,
        ),
        (
            "C011",
            {"order_id": "O0033", "field": "nome", "correct_value": "Lima Ltda"},
            "NOT_ELIGIBLE",
            "escalate_to_human",
        ),
    ],
    "issue_return_invoice": [
        ("C001", {"order_id": "O0001"}, "NOT_ELIGIBLE", "get_refund_status"),
        ("C011", {"order_id": "O0033"}, "NOT_ELIGIBLE", "escalate_to_human"),
    ],
    "get_purchase_receipt": [("C002", {"order_id": "O0005"}, "NOT_ELIGIBLE", "get_payment_status")],
    "update_billing_data": [
        ("C001", {"field": "inscricao_estadual", "new_value": "123"}, "VALIDATION_ERROR", None),
    ],
    "validate_coupon": [("C001", {"code": "NAOEXISTE"}, "NOT_FOUND", None)],
    "report_coupon_not_applied": [
        ("C002", {"order_id": "O0004", "code": "CASA50"}, "NOT_ELIGIBLE", "validate_coupon"),
    ],
    "get_promotion_terms": [("C001", {"promotion": "xyzw"}, "NOT_FOUND", None)],
    "request_price_protection": [
        ("C001", {"order_id": "O0002"}, "NOT_ELIGIBLE", None),
        ("C002", {"order_id": "O0005"}, "NOT_ELIGIBLE", "get_payment_status"),
    ],
    "get_gift_card_balance": [
        ("C001", {"code": "PRESENTE-4K7M2Q"}, "NOT_ELIGIBLE", "redeem_gift_card"),
        ("C002", {}, "NOT_FOUND", None),
    ],
    "redeem_gift_card": [
        ("C001", {"code": "VALE-7Q2K91XA"}, "NOT_ELIGIBLE", "get_gift_card_balance"),
        ("C001", {"code": "PRESENTE-2B9X5R"}, "NOT_ELIGIBLE", "escalate_to_human"),
    ],
    "get_points_balance": [(None, {}, "VALIDATION_ERROR", None)],
    "get_points_statement": [(None, {}, "VALIDATION_ERROR", None)],
    "redeem_points": [
        ("C001", {"points": 550}, "VALIDATION_ERROR", None),
        ("C008", {"points": 500}, "NOT_ELIGIBLE", None),
    ],
    "claim_missing_points": [
        ("C001", {"order_id": "O0001"}, "NOT_ELIGIBLE", "get_points_balance"),
        ("C002", {"order_id": "O0004"}, "NOT_ELIGIBLE", "get_points_statement"),
    ],
    "get_cashback_status": [("C001", {"order_id": "O0001"}, "NOT_ELIGIBLE", None)],
    "get_loyalty_tier": [(None, {}, "VALIDATION_ERROR", None)],
    "get_card_bill": [("C001", {}, "NOT_ELIGIBLE", None)],
    "generate_card_bill_copy": [
        ("C015", {}, "NOT_ELIGIBLE", "get_card_bill"),
        ("C020", {}, "NOT_ELIGIBLE", "renegotiate_debt"),
    ],
    "contest_card_transaction": [
        (
            "C018",
            {"transaction_id": _tx("C018", True), "reason": "duplicada"},
            "NOT_ELIGIBLE",
            "check_protocol_status",
        ),
        ("C018", {"transaction_id": "TX-00000000", "reason": "duplicada"}, "NOT_FOUND", None),
    ],
    "request_limit_increase": [
        ("C009", {"desired_limit": 5000}, "NOT_ELIGIBLE", "get_card_bill"),
        ("C012", {"desired_limit": 5000}, "NOT_ELIGIBLE", "escalate_to_human"),
    ],
    "block_store_card": [("C012", {"reason": "roubo"}, "NOT_ELIGIBLE", "escalate_to_human")],
    "renegotiate_debt": [("C002", {"installments": 3}, "NOT_ELIGIBLE", "get_card_bill")],
    "update_contact_info": [
        ("C001", {}, "VALIDATION_ERROR", None),
        ("C001", {"email": "sem-arroba"}, "VALIDATION_ERROR", None),
    ],
    "check_protocol_status": [
        ("C001", {"protocol": "REF-12345678"}, "NOT_ELIGIBLE", "get_refund_status"),
        ("C001", {"protocol": "xyz"}, "VALIDATION_ERROR", None),
        ("C001", {"protocol": "ZZZ-12345678"}, "NOT_FOUND", None),
    ],
}


def test_error_cases_cover_all_new_tools() -> None:
    assert set(ERRORS_L) == {t.name for t in REGISTRY_LARGE}


@pytest.mark.parametrize(
    ("tool", "case"),
    [(t, c) for t, cases in sorted(ERRORS_L.items()) for c in cases],
    ids=[f"{t}-{i}" for t, cases in sorted(ERRORS_L.items()) for i in range(len(cases))],
)
async def test_new_tool_business_error(large: Client, tool: str, case: tuple) -> None:
    customer, args, code, suggested = case
    schemas = {t.name: t.output_schema for t in await large.list_tools()}
    r = await _call(large, tool, customer, args)
    assert r.is_error, r.content
    sc = r.structured_content
    jsonschema.validate(sc, schemas[tool])
    assert sc["code"] == code and sc["suggested_tool"] == suggested, sc
    assert r.content[0].text.startswith(sc["message"])


async def test_new_tools_are_deterministic_and_receipts_depend_on_args(large: Client) -> None:
    a = await _call(large, "contact_seller", "C001", {"order_id": "O0002", "message": "oi, ok?"})
    b = await _call(large, "contact_seller", "C001", {"order_id": "O0002", "message": "oi, ok?"})
    c = await _call(large, "contact_seller", "C001", {"order_id": "O0002", "message": "outra"})
    assert a.structured_content == b.structured_content
    assert a.structured_content["protocol"] != c.structured_content["protocol"]


async def test_writes_do_not_persist_in_large(large: Client) -> None:
    await _call(large, "cancel_subscription", "C001", {})
    r = await _call(large, "get_subscription", "C001", {})
    assert r.structured_content["subscription_status"] == "active"


async def test_minted_protocol_is_recognised(large: Client) -> None:
    r = await _call(large, "update_contact_info", "C001", {"phone": "(11) 98888-7766"})
    proto = r.structured_content["protocol"]
    s = await _call(large, "check_protocol_status", "C001", {"protocol": proto.lower()})
    assert not s.is_error and s.structured_content["kind"] == "dados_contato"


async def test_large_help_center_has_new_articles(large: Client, small: Client) -> None:
    q = {"query": "como funciona a garantia estendida"}
    r = await _call(large, "search_help_center", "C001", q)
    assert "HC-012" in {a["id"] for a in r.structured_content["articles"]}
    r = await _call(small, "search_help_center", "C001", q)
    assert "HC-012" not in {a["id"] for a in r.structured_content["articles"]}


# ------------------------------------------------------------------ leakage


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _overlaps(a: str, b: str, min_words: int = 4) -> bool:
    short, long_ = sorted((a, b), key=len)
    return a == b or (len(short.split()) >= min_words and f" {short} " in f" {long_} ")


async def test_large_catalog_text_does_not_leak_phase1_messages(large: Client) -> None:
    """New examples (tool `_meta` and SKILL.md frontmatter) vs every phase-1 split."""
    messages: dict[str, str] = {}
    for split in PHASE1_SPLITS:
        for line in (DATA / split).read_text(encoding="utf-8").splitlines():
            if line.strip():
                case = json.loads(line)
                for turn in case["turns"]:
                    if turn["role"] == "user":
                        messages[_norm(turn["content"])] = f"{split}:{case['id']}"
    texts = [(t.name, e) for t in REGISTRY_LARGE for e in t.meta[f"{RDNS}/examples"]]
    texts += [("escalate_to_human", e) for e in EXAMPLES["escalate_to_human"]]
    texts += [(s, e) for s in SKILL_IDS_LARGE[3:] for e in _skill(s)[0]["examples"]]
    leaks = [
        f"{name}: {text!r} ~ {case}"
        for name, text in texts
        for message, case in messages.items()
        if _overlaps(_norm(text), message)
    ]
    assert not leaks, "\n".join(leaks)
