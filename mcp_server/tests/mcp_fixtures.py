"""Shared helpers for the MCP server tests (unique module name to avoid rootdir clashes)."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from mcp_server.core import CUSTOMER_META_KEY, DB, PAYMENTS, SHIPMENTS, TODAY
from mcp_server.server import PROFILES, build_server

# one server per catalog profile (conftest's `client` fixture is parametrized over them)
SERVERS = {p: build_server(p) for p in PROFILES}


def meta(customer_id: str | None) -> dict[str, Any]:
    return {CUSTOMER_META_KEY: customer_id} if customer_id else {}


def delivered_days(order: dict[str, Any]) -> int | None:
    if not order["delivered_at"]:
        return None
    return (TODAY - date.fromisoformat(order["delivered_at"])).days


def find_order(pred: Callable[[dict[str, Any]], bool]) -> tuple[str, str]:
    """(customer_id, order_id) of the first mock order matching `pred`."""
    for order in DB["orders"]:
        if pred(order):
            return order["customer_id"], order["id"]
    raise LookupError("no mock order matches")


def pay(order: dict[str, Any]) -> dict[str, Any]:
    return PAYMENTS[order["payment_id"]]


def ship_status(order: dict[str, Any]) -> str | None:
    return SHIPMENTS[order["shipment_id"]]["status"] if order["shipment_id"] else None


def large_variants(tool: str, cid: str, oid: str) -> list[dict[str, Any]] | None:
    """Plausible argument sets for a new (large-profile) tool, for customer `cid` and order
    `oid`; None when `tool` is not a large-profile tool."""
    from mcp_server.large.data import DB_L

    o = {"order_id": oid}
    sub = [s["id"] for s in DB_L["subscriptions"] if s["customer_id"] == cid][:1]
    os_ = [s["id"] for s in DB_L["service_orders"] if s["customer_id"] == cid][:1]
    card = next((c for c in DB_L["store_cards"] if c["customer_id"] == cid), None)
    txs = [t["id"] for t in card["bill"]["transactions"]][:1] if card else ["TX-00000000"]
    protos = [p["id"] for p in DB_L["protocols"] if p["customer_id"] == cid][:1] or ["ATD-00000000"]
    s = {"subscription_id": sub[0]} if sub else {}
    so = {"service_order_id": os_[0]} if os_ else {}
    day = (TODAY + timedelta(days=4)).isoformat()
    table: dict[str, list[dict[str, Any]]] = {
        "schedule_installation": [{**o, "date": day}],
        "request_technical_visit": [{**o, "date": day, "problem_description": "parou"}],
        "reschedule_technical_visit": [{**so, "new_date": day}],
        "get_service_order_status": [so],
        "cancel_service_order": [so],
        "check_extended_warranty": [o],
        "get_seller_info": [o],
        "contact_seller": [{**o, "message": "Quando chega?"}],
        "track_seller_shipment": [o],
        "open_seller_mediation": [{**o, "reason": "sem_resposta"}],
        "report_seller_issue": [{**o, "issue_type": "outro", "details": "anúncio confuso"}],
        "rate_seller": [{**o, "rating": 4}],
        "get_subscription": [s],
        "pause_subscription": [{**s, "cycles": 1}],
        "cancel_subscription": [s],
        "change_subscription_date": [{**s, "new_date": day}],
        "change_subscription_items": [{**s, "sku": "CAF-GRAO-1K", "quantity": 1}],
        "update_subscription_payment": [{**s, "method": "pix"}],
        "get_invoice": [o],
        "resend_invoice": [o],
        "request_invoice_correction": [{**o, "field": "nome", "correct_value": "Nome Certo"}],
        "issue_return_invoice": [o],
        "get_purchase_receipt": [o],
        "update_billing_data": [{"field": "nome", "new_value": "Nome Novo"}],
        "validate_coupon": [{"code": "CASA50"}],
        "report_coupon_not_applied": [{**o, "code": "PRIMAVERA30"}],
        "get_promotion_terms": [{"promotion": "SEMANA-CASA"}],
        "request_price_protection": [o],
        "get_gift_card_balance": [{}],
        "redeem_gift_card": [{"code": "PRESENTE-4K7M2Q"}],
        "get_points_balance": [{}],
        "get_points_statement": [{}],
        "redeem_points": [{"points": 500}],
        "claim_missing_points": [o],
        "get_cashback_status": [o],
        "get_loyalty_tier": [{}],
        "get_card_bill": [{}],
        "generate_card_bill_copy": [{}],
        "contest_card_transaction": [{"transaction_id": txs[0], "reason": "duplicada"}],
        "request_limit_increase": [
            {"desired_limit": (card["limit"]["amount"] if card else 1000.0) + 500}
        ],
        "block_store_card": [{"reason": "perda"}],
        "renegotiate_debt": [{"installments": 6}],
        "update_contact_info": [{"phone": "11988887766"}],
        "check_protocol_status": [{"protocol": protos[0]}],
    }
    return table.get(tool)
