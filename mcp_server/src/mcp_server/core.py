"""Shared runtime: read-only mock DB, request customer, deterministic receipts, result helpers,
and the tool registry used by the tools/* modules."""

from __future__ import annotations

import functools
import hashlib
import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import date, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any

from fastmcp.tools.base import ToolResult
from fastmcp.tools.function_tool import FunctionTool
from mcp.types import TextContent, ToolAnnotations
from pydantic import BaseModel

from mcp_server.models import Address, ErrorCode, ErrorResult, Money, OrderRef, output_schema

PKG_DIR = Path(__file__).resolve().parent
RDNS = "br.routingstudy"
CUSTOMER_META_KEY = f"{RDNS}/customer_id"


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((PKG_DIR / name).read_text(encoding="utf-8"))


DB: dict[str, Any] = _load_json("mock_db.json")
POLICIES: dict[str, Any] = _load_json("policies.json")
TODAY = date.fromisoformat(DB["reference_date"])

CUSTOMERS = MappingProxyType({c["id"]: c for c in DB["customers"]})
ORDERS = MappingProxyType({o["id"]: o for o in DB["orders"]})
PAYMENTS = MappingProxyType({p["id"]: p for p in DB["payments"]})
SHIPMENTS = MappingProxyType({s["id"]: s for s in DB["shipments"]})
REFUNDS_BY_ORDER = MappingProxyType({r["order_id"]: r for r in DB["refunds"]})
RETURNS = MappingProxyType({r["id"]: r for r in DB["returns"]})

current_customer_id: ContextVar[str | None] = ContextVar("current_customer_id", default=None)


class ToolFailure(Exception):
    """Business-rule failure, returned as `isError: true` + ErrorResult."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        recoverable: bool,
        suggested_tool: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error = ErrorResult(
            code=code,
            message=message,
            recoverable=recoverable,
            suggested_tool=suggested_tool,
            details=details,
        )


def ok(result: BaseModel, text: str) -> ToolResult:
    return ToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=result.model_dump(mode="json"),
    )


def fail(error: ErrorResult) -> ToolResult:
    text = error.message
    if error.suggested_tool:
        text += f" Próxima ação sugerida: {error.suggested_tool}."
    return ToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=error.model_dump(mode="json"),
        is_error=True,
    )


def protocol(prefix: str, tool: str, args: dict[str, Any]) -> str:
    """Deterministic receipt: sha256(tool, customer, args)[:8]. Writes never persist."""
    payload = json.dumps(
        {"tool": tool, "customer": current_customer_id.get(), "args": args},
        sort_keys=True,
        ensure_ascii=False,
    )
    return f"{prefix}-{hashlib.sha256(payload.encode()).hexdigest()[:8].upper()}"


def days_from_today(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def brl(money: dict[str, Any] | Money) -> str:
    amount = money.amount if isinstance(money, Money) else money["amount"]
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def fmt_address(a: dict[str, Any] | Address) -> str:
    a = a if isinstance(a, Address) else Address(**a)
    comp = f", {a.complement}" if a.complement else ""
    return (
        f"{a.street}, {a.number}{comp}, {a.neighborhood}, {a.city}/{a.state}, "
        f"CEP {a.postal_code[:5]}-{a.postal_code[5:]}"
    )


def get_customer() -> dict[str, Any]:
    cid = current_customer_id.get()
    if not cid:
        raise ToolFailure(
            "VALIDATION_ERROR",
            "Cliente não identificado na requisição.",
            recoverable=False,
        )
    customer = CUSTOMERS.get(cid)
    if customer is None:
        raise ToolFailure(
            "NOT_FOUND",
            f"Cliente {cid} não encontrado.",
            recoverable=False,
        )
    return customer


def order_ref(order: dict[str, Any]) -> OrderRef:
    return OrderRef(
        order_id=order["id"],
        status=order["status"],
        created_at=order["created_at"],
        total=Money(**order["total"]),
    )


def resolve_order(order_id: str | None) -> dict[str, Any]:
    """Customer's order by id; when omitted, the customer's only order."""
    customer = get_customer()
    owned = customer["order_ids"]
    if order_id is None or not order_id.strip():
        if len(owned) == 1:
            return ORDERS[owned[0]]
        raise ToolFailure(
            "VALIDATION_ERROR",
            f"O cliente tem {len(owned)} pedidos; informe order_id.",
            recoverable=True,
            details={"options": list(owned)},
        )
    oid = order_id.strip().upper()
    if oid.isdigit():
        oid = f"O{int(oid):04d}"
    if oid not in owned:
        raise ToolFailure(
            "NOT_FOUND",
            f"Pedido {order_id.strip()} não encontrado para este cliente.",
            recoverable=True,
            suggested_tool="get_customer_profile",
            details={"options": list(owned)},
        )
    return ORDERS[oid]


def pick_sku(order: dict[str, Any], sku: str | None) -> dict[str, Any]:
    items = order["items"]
    if sku is None or not sku.strip():
        if len(items) == 1:
            return items[0]
        raise ToolFailure(
            "VALIDATION_ERROR",
            f"O pedido {order['id']} tem {len(items)} itens; informe sku.",
            recoverable=True,
            details={"options": [i["sku"] for i in items]},
        )
    for item in items:
        if item["sku"] == sku.strip().upper():
            return item
    raise ToolFailure(
        "NOT_FOUND",
        f"Item {sku} não pertence ao pedido {order['id']}.",
        recoverable=True,
        details={"options": [i["sku"] for i in items]},
    )


def open_return(order: dict[str, Any]) -> dict[str, Any] | None:
    return next((r for r in RETURNS.values() if r["order_id"] == order["id"]), None)


def ensure_no_money_back(order: dict[str, Any]) -> None:
    """Refuse a new return/exchange/dispute while a refund or return is already open."""
    refund = REFUNDS_BY_ORDER.get(order["id"])
    if refund is not None:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Já existe o reembolso {refund['id']} (status {refund['status']}) para o pedido "
            f"{order['id']}.",
            recoverable=False,
            suggested_tool="get_refund_status",
        )
    ret = open_return(order)
    if ret is not None:
        raise ToolFailure(
            "NOT_ELIGIBLE",
            f"Já existe a devolução {ret['id']} aberta para o pedido {order['id']}.",
            recoverable=False,
            suggested_tool="generate_return_label",
        )


def days_since_delivery(order: dict[str, Any]) -> int | None:
    if not order["delivered_at"]:
        return None
    return (TODAY - date.fromisoformat(order["delivered_at"])).days


def after_delivery_next_step(order: dict[str, Any]) -> str:
    """Tool that can succeed next for a delivered order (refund, return label, return, or
    the eligibility summary when every window is closed)."""
    if order["id"] in REFUNDS_BY_ORDER:
        return "get_refund_status"
    if open_return(order) is not None:
        return "generate_return_label"
    days = days_since_delivery(order)
    if days is not None and days <= POLICIES["windows"]["return_or_exchange_days_after_delivery"]:
        return "create_return_request"
    return "check_return_eligibility"


def money_back_next_step(order: dict[str, Any]) -> str:
    """Tool that can succeed next when the customer wants money back for this order."""
    if order["id"] in REFUNDS_BY_ORDER:
        return "get_refund_status"
    if PAYMENTS[order["payment_id"]]["status"] != "approved":
        return "get_payment_status"
    lost = bool(order["shipment_id"]) and SHIPMENTS[order["shipment_id"]]["status"] == "lost"
    if order["status"] == "cancelled" or lost:
        return "request_refund"
    if order["status"] in ("awaiting_payment", "processing"):
        return "cancel_order"
    if order["delivered_at"]:
        return after_delivery_next_step(order)
    return "track_shipment"


# ---------------------------------------------------------------- tool registry

READ = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
)
DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
)


class CatalogTool(FunctionTool):
    """FunctionTool whose `_meta` carries only our reverse-DNS keys (drops `fastmcp` key)."""

    def get_meta(self) -> dict[str, Any]:
        meta = super().get_meta()
        meta.pop("fastmcp", None)
        return meta


REGISTRY: list[CatalogTool] = []


def catalog_tool(
    *,
    skill: str,
    scope: str,
    title: str,
    description: str,
    annotations: ToolAnnotations,
    result: type[BaseModel],
    examples: list[str],
    keywords: list[str],
    registry: list[CatalogTool] | None = None,
) -> Callable[[Callable[..., Awaitable[ToolResult]]], Callable[..., Awaitable[ToolResult]]]:
    """Register a tool: business errors raised as ToolFailure become isError results.

    `registry`: where to register (default REGISTRY, the small profile's 18 tools)."""
    assert 3 <= len(examples) <= 5, "3-5 examples per tool"

    def decorator(
        fn: Callable[..., Awaitable[ToolResult]],
    ) -> Callable[..., Awaitable[ToolResult]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> ToolResult:
            try:
                return await fn(*args, **kwargs)
            except ToolFailure as exc:
                return fail(exc.error)

        meta: dict[str, Any] = {
            f"{RDNS}/skill": skill,
            f"{RDNS}/examples": examples,
            f"{RDNS}/keywords": keywords,
            f"{RDNS}/confirmation": "none",
            f"{RDNS}/scope": scope,
        }
        if not annotations.read_only_hint:
            meta[f"{RDNS}/elicitation"] = []
        (REGISTRY if registry is None else registry).append(
            CatalogTool.from_function(
                wrapper,
                name=fn.__name__,
                title=title,
                description=description.strip(),
                annotations=annotations,
                output_schema=output_schema(result),
                meta=meta,
            )
        )
        return wrapper

    return decorator


REFUND_DAYS = {"credit_card": 60, "pix": 7, "boleto": 14}
REFUND_TEXT = {
    "credit_card": "estorno no cartão em até 2 faturas",
    "pix": "devolução via Pix em até 5 dias úteis",
    "boleto": "depósito na conta bancária em até 10 dias úteis",
}


def refund_deadline(method: str) -> str:
    """Last calendar day for the refund to land, by payment method (see shop://policies)."""
    return days_from_today(REFUND_DAYS[method])
