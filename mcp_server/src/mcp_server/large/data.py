"""Large-profile runtime: read-only `mock_db_large.json` + `policies_large.json`, entity
lookups for the 7 new skills and the new globals, and `REGISTRY_LARGE` (the 44 new tools).

The large DB embeds the small DB unchanged (asserted at import), so the 18 original tools keep
reading `mcp_server.core` and see exactly the same customers, orders and payments.
"""

from __future__ import annotations

import functools
import json
from datetime import date
from types import MappingProxyType
from typing import Any

from mcp_server.core import (
    DB,
    ORDERS,
    PAYMENTS,
    PKG_DIR,
    TODAY,
    CatalogTool,
    ToolFailure,
    catalog_tool,
    get_customer,
    resolve_order,
)

DB_L: dict[str, Any] = json.loads((PKG_DIR / "mock_db_large.json").read_text(encoding="utf-8"))
POLICIES_L: dict[str, Any] = json.loads(
    (PKG_DIR / "policies_large.json").read_text(encoding="utf-8")
)
for _key in (
    "reference_date",
    "customers",
    "orders",
    "payments",
    "shipments",
    "refunds",
    "returns",
):
    assert DB_L[_key] == DB[_key], f"mock_db_large.json diverges from mock_db.json on {_key}"
W = POLICIES_L["windows"]
SLA = POLICIES_L["sla"]

SELLERS = MappingProxyType({s["id"]: s for s in DB_L["sellers"]})
MARKETPLACE = MappingProxyType({m["order_id"]: m for m in DB_L["marketplace_orders"]})
SERVICE_ORDERS = MappingProxyType({s["id"]: s for s in DB_L["service_orders"]})
EXT_WARRANTY_BY_ORDER = MappingProxyType({w["order_id"]: w for w in DB_L["extended_warranties"]})
SUBSCRIPTIONS = MappingProxyType({s["id"]: s for s in DB_L["subscriptions"]})
BILLING = MappingProxyType({b["customer_id"]: b for b in DB_L["billing_profiles"]})
INVOICES_BY_ORDER = MappingProxyType({i["order_id"]: i for i in DB_L["invoices"]})
COUPONS = MappingProxyType({c["code"]: c for c in DB_L["coupons"]})
PROMOTIONS = MappingProxyType({p["id"]: p for p in DB_L["promotions"]})
CURRENT_PRICES = MappingProxyType({p["sku"]: p["price"] for p in DB_L["current_prices"]})
GIFT_CARDS = MappingProxyType({g["code"]: g for g in DB_L["gift_cards"]})
LOYALTY = MappingProxyType({a["customer_id"]: a for a in DB_L["loyalty_accounts"]})
CASHBACK_BY_ORDER = MappingProxyType({c["order_id"]: c for c in DB_L["cashback"]})
STORE_CARDS = MappingProxyType({c["customer_id"]: c for c in DB_L["store_cards"]})
PROTOCOLS = MappingProxyType({p["id"]: p for p in DB_L["protocols"]})

REGISTRY_LARGE: list[CatalogTool] = []
large_tool = functools.partial(catalog_tool, registry=REGISTRY_LARGE)


def days_since(iso: str) -> int:
    return (TODAY - date.fromisoformat(iso)).days


def future_date(value: str, lo: int, hi: int) -> date:
    """`value` (AAAA-MM-DD) between lo and hi days after TODAY, else a recoverable error."""
    try:
        wanted = date.fromisoformat(value.strip())
    except ValueError:
        wanted = None
    if wanted is None or not lo <= (wanted - TODAY).days <= hi:
        raise ToolFailure(
            "VALIDATION_ERROR",
            f"A data deve estar no formato AAAA-MM-DD, entre {lo} e {hi} dias após {TODAY}.",
            recoverable=True,
        )
    return wanted


def resolve_owned(
    entity_id: str | None, owned: list[str], label: str, param: str, table: Any
) -> dict[str, Any]:
    """The customer's entity by id; when omitted, the only one. Same contract as orders:
    several -> VALIDATION_ERROR with details.options; not the customer's -> NOT_FOUND."""
    if entity_id is None or not entity_id.strip():
        if len(owned) == 1:
            return table[owned[0]]
        if not owned:
            raise ToolFailure("NOT_FOUND", f"O cliente não tem {label}.", recoverable=False)
        raise ToolFailure(
            "VALIDATION_ERROR",
            f"O cliente tem {len(owned)} {label}; informe {param}.",
            recoverable=True,
            details={"options": list(owned)},
        )
    eid = entity_id.strip().upper()
    if eid not in owned:
        raise ToolFailure(
            "NOT_FOUND",
            f"{entity_id.strip()} não encontrado para este cliente.",
            recoverable=True,
            details={"options": list(owned)},
        )
    return table[eid]


def resolve_subscription(subscription_id: str | None) -> dict[str, Any]:
    cid = get_customer()["id"]
    owned = [s["id"] for s in SUBSCRIPTIONS.values() if s["customer_id"] == cid]
    return resolve_owned(subscription_id, owned, "assinatura(s)", "subscription_id", SUBSCRIPTIONS)


def resolve_service_order(service_order_id: str | None) -> dict[str, Any]:
    cid = get_customer()["id"]
    owned = [s["id"] for s in SERVICE_ORDERS.values() if s["customer_id"] == cid]
    return resolve_owned(
        service_order_id, owned, "ordem(ns) de serviço", "service_order_id", SERVICE_ORDERS
    )


def store_card() -> dict[str, Any]:
    card = STORE_CARDS.get(get_customer()["id"])
    if card is None:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            "O cliente não tem cartão da loja.",
            recoverable=False,
        )
    return card


def marketplace_order(order_id: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """(order, marketplace record) for an order sold and shipped by a partner seller."""
    o = resolve_order(order_id)
    mk = MARKETPLACE.get(o["id"])
    if mk is None:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"O pedido {o['id']} foi vendido e entregue pela própria loja, não por um vendedor "
            "parceiro.",
            recoverable=False,
            suggested_tool="track_shipment" if o["shipment_id"] else "get_order_status",
        )
    return o, mk


def customer_card_last4s(customer: dict[str, Any]) -> list[str]:
    """Cards the customer already used (wallet): credit-card payments of their orders."""
    return sorted(
        {
            last4
            for oid in customer["order_ids"]
            if (last4 := PAYMENTS[ORDERS[oid]["payment_id"]]["card_last4"])
        }
    )


def mask_email(email: str) -> str:
    user, domain = email.split("@", 1)
    return f"{user[0]}***@{domain}"
