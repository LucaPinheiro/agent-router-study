"""Shared helpers for the MCP server tests (unique module name to avoid rootdir clashes)."""

from collections.abc import Callable
from datetime import date
from typing import Any

from mcp_server.core import CUSTOMER_META_KEY, DB, PAYMENTS, SHIPMENTS, TODAY


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
