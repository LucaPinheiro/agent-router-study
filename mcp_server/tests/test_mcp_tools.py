from datetime import timedelta
from typing import Any

import jsonschema
import pytest
from fastmcp import Client
from mcp_fixtures import delivered_days, find_order, meta, pay, ship_status
from mcp_server.core import DB, ORDERS, REFUNDS_BY_ORDER, RETURNS, TODAY

EXPECTED_TOOLS = {
    "global": {"get_customer_profile", "search_help_center", "escalate_to_human"},
    "pedidos_logistica": {
        "get_order_status",
        "track_shipment",
        "update_delivery_address",
        "reschedule_delivery",
        "cancel_order",
    },
    "pagamentos_reembolsos": {
        "get_payment_status",
        "generate_boleto_second_copy",
        "request_refund",
        "get_refund_status",
        "dispute_charge",
    },
    "trocas_devolucoes": {
        "check_return_eligibility",
        "create_return_request",
        "generate_return_label",
        "create_exchange",
        "open_warranty_claim",
    },
}
EXPECTED_TOOLS_LARGE = {
    **EXPECTED_TOOLS,
    "global": EXPECTED_TOOLS["global"] | {"update_contact_info", "check_protocol_status"},
    "assistencia_tecnica": {
        "schedule_installation",
        "request_technical_visit",
        "reschedule_technical_visit",
        "get_service_order_status",
        "cancel_service_order",
        "check_extended_warranty",
    },
    "marketplace_vendedores": {
        "get_seller_info",
        "contact_seller",
        "track_seller_shipment",
        "open_seller_mediation",
        "report_seller_issue",
        "rate_seller",
    },
    "assinaturas": {
        "get_subscription",
        "pause_subscription",
        "cancel_subscription",
        "change_subscription_date",
        "change_subscription_items",
        "update_subscription_payment",
    },
    "notas_fiscais_cadastro": {
        "get_invoice",
        "resend_invoice",
        "request_invoice_correction",
        "issue_return_invoice",
        "get_purchase_receipt",
        "update_billing_data",
    },
    "promocoes_precos": {
        "validate_coupon",
        "report_coupon_not_applied",
        "get_promotion_terms",
        "request_price_protection",
        "get_gift_card_balance",
        "redeem_gift_card",
    },
    "fidelidade_cashback": {
        "get_points_balance",
        "get_points_statement",
        "redeem_points",
        "claim_missing_points",
        "get_cashback_status",
        "get_loyalty_tier",
    },
    "cartao_loja_crediario": {
        "get_card_bill",
        "generate_card_bill_copy",
        "contest_card_transaction",
        "request_limit_increase",
        "block_store_card",
        "renegotiate_debt",
    },
}
EXPECTED_BY_PROFILE = {"small": EXPECTED_TOOLS, "large": EXPECTED_TOOLS_LARGE}
DESTRUCTIVE_BY_PROFILE = {
    "small": {"cancel_order", "dispute_charge"},
    "large": {
        "cancel_order",
        "dispute_charge",
        "cancel_subscription",
        "cancel_service_order",
        "block_store_card",
    },
}
RDNS = "br.routingstudy"
ADDRESS = {
    "street": "Rua Bahia",
    "number": "90",
    "neighborhood": "Higienópolis",
    "city": "São Paulo",
    "state": "SP",
    "postal_code": "01244-000",
}


def first_sku(order_id: str) -> str:
    return ORDERS[order_id]["items"][0]["sku"]


def _case(pred: Any, **args: Any) -> tuple[str, dict[str, Any]]:
    cid, oid = find_order(pred)
    return cid, {"order_id": oid, **args}


def _delivered_within(lo: int, hi: int) -> Any:
    return lambda o: (d := delivered_days(o)) is not None and lo <= d <= hi


_return_c, _return_a = _case(lambda o: any(r["order_id"] == o["id"] for r in RETURNS.values()))


def _no_money_back(o: dict[str, Any]) -> bool:
    return o["id"] not in REFUNDS_BY_ORDER and not any(
        r["order_id"] == o["id"] for r in RETURNS.values()
    )


_exch_c, _exch_a = _case(lambda o: _delivered_within(0, 30)(o) and _no_money_back(o))
_warr_c, _warr_a = _case(_delivered_within(31, 365))
_arrep = _delivered_within(0, 7)

HAPPY: dict[str, tuple[str, dict[str, Any]]] = {
    "get_customer_profile": ("C001", {}),
    "search_help_center": ("C001", {"query": "qual o prazo para devolver"}),
    "escalate_to_human": ("C001", {"reason": "quero falar com um atendente"}),
    "get_order_status": _case(lambda o: True),
    "track_shipment": _case(lambda o: o["shipment_id"] is not None),
    "update_delivery_address": _case(lambda o: o["status"] == "processing", **ADDRESS),
    "reschedule_delivery": _case(
        lambda o: ship_status(o) == "delivery_failed",
        new_date=(TODAY + timedelta(days=3)).isoformat(),
        period="tarde",
    ),
    "cancel_order": _case(lambda o: o["status"] == "processing"),
    "get_payment_status": _case(lambda o: True),
    "generate_boleto_second_copy": _case(
        lambda o: pay(o)["method"] == "boleto" and pay(o)["status"] == "pending"
    ),
    "request_refund": _case(lambda o: ship_status(o) == "lost", reason="pedido extraviado"),
    "get_refund_status": _case(lambda o: o["id"] in REFUNDS_BY_ORDER),
    "dispute_charge": _case(
        lambda o: (
            pay(o)["method"] == "credit_card"
            and pay(o)["status"] == "approved"
            and o["status"] == "processing"
        ),
        reason="duplicada",
    ),
    "check_return_eligibility": _case(_delivered_within(0, 400)),
    "create_return_request": _case(
        lambda o: _arrep(o) and not any(r["order_id"] == o["id"] for r in RETURNS.values()),
        reason="arrependimento",
    ),
    "generate_return_label": (_return_c, _return_a),
    "create_exchange": (
        _exch_c,
        {**_exch_a, "sku": first_sku(_exch_a["order_id"]), "new_variant": "41"},
    ),
    "open_warranty_claim": (
        _warr_c,
        {**_warr_a, "sku": first_sku(_warr_a["order_id"]), "defect_description": "parou de ligar"},
    ),
}

_multi = next(c["id"] for c in DB["customers"] if len(c["order_ids"]) > 1)

ERRORS: dict[str, tuple[str | None, dict[str, Any], str, str | None]] = {
    # tool: (customer, args, code, suggested_tool)
    # every tool (escalate_to_human included) needs the customer: no tool can recover
    "get_customer_profile": (None, {}, "VALIDATION_ERROR", None),
    "search_help_center": ("C001", {"query": "xablau zzzqqq"}, "NOT_FOUND", "escalate_to_human"),
    "escalate_to_human": (
        "C001",
        {"reason": "ajuda", "order_id": "O9999"},
        "NOT_FOUND",
        "get_customer_profile",
    ),
    "get_order_status": (_multi, {}, "VALIDATION_ERROR", None),
    "track_shipment": (
        *_case(lambda o: o["status"] == "processing"),
        "NOT_ELIGIBLE",
        "get_order_status",
    ),
    "update_delivery_address": (
        *_case(lambda o: o["status"] == "delivered", **ADDRESS),
        "NOT_ELIGIBLE",
        "escalate_to_human",
    ),
    "reschedule_delivery": (
        *_case(lambda o: ship_status(o) == "in_transit", new_date="2020-01-01"),
        "VALIDATION_ERROR",
        None,
    ),
    "cancel_order": (
        *_case(lambda o: _delivered_within(0, 30)(o) and _no_money_back(o)),
        "NOT_ELIGIBLE",
        "create_return_request",
    ),
    "get_payment_status": ("C001", {"order_id": "O9999"}, "NOT_FOUND", "get_customer_profile"),
    "generate_boleto_second_copy": (
        *_case(lambda o: pay(o)["method"] == "credit_card"),
        "NOT_ELIGIBLE",
        "get_payment_status",
    ),
    "request_refund": (
        *_case(
            lambda o: (
                o["status"] == "delivered"
                and pay(o)["status"] == "approved"
                and o["id"] not in REFUNDS_BY_ORDER
            ),
            reason="quero",
        ),
        "NOT_ELIGIBLE",
        "create_return_request",
    ),
    "get_refund_status": (
        *_case(lambda o: o["id"] not in REFUNDS_BY_ORDER and o["status"] == "cancelled"),
        "NOT_ELIGIBLE",  # the order exists: no refund yet is a business precondition
        "request_refund",
    ),
    "dispute_charge": (
        *_case(
            lambda o: pay(o)["method"] == "pix" and o["status"] == "cancelled",
            reason="nao_reconhecida",
        ),
        "NOT_ELIGIBLE",
        "request_refund",
    ),
    "check_return_eligibility": (
        *_case(lambda o: o["status"] == "in_transit"),
        "NOT_ELIGIBLE",
        "track_shipment",
    ),
    "create_return_request": (
        *_case(_delivered_within(31, 365), reason="defeito"),
        "NOT_ELIGIBLE",
        "open_warranty_claim",
    ),
    "generate_return_label": (
        *_case(
            lambda o: (
                o["status"] == "delivered"
                and not any(r["order_id"] == o["id"] for r in RETURNS.values())
            )
        ),
        "NOT_ELIGIBLE",  # the order exists: no return yet is a business precondition
        None,  # D3: never back to create_return_request (loop); the message asks return_id
    ),
    "create_exchange": (
        *_case(_delivered_within(31, 400), new_variant="G"),
        "NOT_ELIGIBLE",
        "open_warranty_claim",
    ),
    "open_warranty_claim": (
        *_case(
            lambda o: _delivered_within(0, 30)(o) and _no_money_back(o),
            defect_description="quebrou",
        ),
        "NOT_ELIGIBLE",
        "create_return_request",
    ),
}


@pytest.fixture
async def schemas(client: Client) -> dict[str, dict[str, Any]]:
    return {t.name: t.output_schema for t in await client.list_tools()}


async def test_tools_list_catalog(client: Client, profile: str) -> None:
    result = await client.list_tools_mcp()
    names = [t.name for t in result.tools]
    expected = EXPECTED_BY_PROFILE[profile]
    assert len(names) == {"small": 18, "large": 62}[profile]
    assert names == sorted(names)
    assert set(names) == set().union(*expected.values())
    assert "load_skill" not in names
    assert result.ttl_ms and result.cache_scope == "public"
    for t in result.tools:
        m = t.meta or {}
        assert set(m) >= {
            f"{RDNS}/{k}" for k in ("skill", "examples", "keywords", "confirmation", "scope")
        }
        assert "fastmcp" not in m
        assert t.name in expected[m[f"{RDNS}/skill"]]
        assert 3 <= len(m[f"{RDNS}/examples"]) <= 5
        assert m[f"{RDNS}/keywords"] and m[f"{RDNS}/confirmation"] == "none"
        for section in ("WHEN TO USE", "DON'T USE FOR", "PARAMETERS", "CONFIRMATION", "RESULT"):
            assert section in (t.description or "")
        assert t.input_schema.get("additionalProperties") is False
        out = t.output_schema or {}
        assert len(out["oneOf"]) == 2 and {"Money", "Address", "OrderRef"} <= set(out["$defs"])
        ann = t.annotations
        assert ann is not None and ann.open_world_hint is False
        destructive = t.name in DESTRUCTIVE_BY_PROFILE[profile]
        assert ann.destructive_hint is destructive
        if ann.read_only_hint:
            assert ann.idempotent_hint is True and not destructive


def test_cases_cover_all_tools() -> None:
    all_tools = set().union(*EXPECTED_TOOLS.values())
    assert set(HAPPY) == all_tools and set(ERRORS) == all_tools


@pytest.mark.parametrize("tool", sorted(HAPPY))
async def test_happy_path(client: Client, schemas: dict[str, Any], tool: str) -> None:
    customer, args = HAPPY[tool]
    r = await client.call_tool(tool, args, meta=meta(customer), raise_on_error=False)
    assert not r.is_error, r.content
    assert r.structured_content["status"] == "completed"
    jsonschema.validate(r.structured_content, schemas[tool])
    assert r.content[0].text


@pytest.mark.parametrize("tool", sorted(ERRORS))
async def test_business_error(client: Client, schemas: dict[str, Any], tool: str) -> None:
    customer, args, code, suggested = ERRORS[tool]
    r = await client.call_tool(tool, args, meta=meta(customer), raise_on_error=False)
    assert r.is_error
    sc = r.structured_content
    jsonschema.validate(sc, schemas[tool])
    assert sc["status"] == "error" and sc["code"] == code
    assert isinstance(sc["recoverable"], bool)
    assert sc["suggested_tool"] == suggested
    assert r.content[0].text.startswith(sc["message"])


async def test_missing_order_id_lists_options(client: Client) -> None:
    r = await client.call_tool("get_order_status", {}, meta=meta(_multi), raise_on_error=False)
    sc = r.structured_content
    assert sc["recoverable"] is True
    assert sc["details"]["options"] == next(
        c["order_ids"] for c in DB["customers"] if c["id"] == _multi
    )


async def test_other_customers_order_is_not_found(client: Client) -> None:
    other = next(o["id"] for o in DB["orders"] if o["customer_id"] != "C001")
    r = await client.call_tool(
        "get_order_status", {"order_id": other}, meta=meta("C001"), raise_on_error=False
    )
    assert r.is_error and r.structured_content["code"] == "NOT_FOUND"


@pytest.mark.parametrize("tool", sorted(HAPPY))
async def test_deterministic(client: Client, tool: str) -> None:
    customer, args = HAPPY[tool]
    a = await client.call_tool(tool, args, meta=meta(customer), raise_on_error=False)
    b = await client.call_tool(tool, args, meta=meta(customer), raise_on_error=False)
    assert a.structured_content == b.structured_content
    assert a.content[0].text == b.content[0].text


async def test_writes_do_not_persist(client: Client) -> None:
    customer, args = HAPPY["cancel_order"]
    await client.call_tool("cancel_order", args, meta=meta(customer))
    r = await client.call_tool(
        "get_order_status", {"order_id": args["order_id"]}, meta=meta(customer)
    )
    assert r.structured_content["order"]["status"] == "processing"


async def test_receipt_depends_on_args(client: Client) -> None:
    customer, args = HAPPY["escalate_to_human"]
    a = await client.call_tool("escalate_to_human", args, meta=meta(customer))
    b = await client.call_tool("escalate_to_human", {"reason": "outro motivo"}, meta=meta(customer))
    ta, tb = a.structured_content["ticket_id"], b.structured_content["ticket_id"]
    assert ta != tb and ta.startswith("ATD-") and len(ta) == len("ATD-") + 8


async def test_schema_invalid_args_rejected(client: Client) -> None:
    r = await client.call_tool(
        "get_order_status",
        {"order_id": "O0001", "extra": 1},
        meta=meta("C001"),
        raise_on_error=False,
    )
    assert r.is_error and r.structured_content is None
