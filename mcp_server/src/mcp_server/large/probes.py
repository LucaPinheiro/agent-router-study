"""Canonical calls of the 44 new tools per mock entity (large profile).

Used by `scripts/generate_mock_db_large.py` (MOCK_DB_NOTES_LARGE.md `compatible_tools`) and by
the large-profile tests (every tool completes on at least one entity). A probe is
(entity kind, entity id, customer, archetype, [(label, tool, args)]); the label is the tool name,
plus the distinguishing argument when the tool takes one the dataset generator must reuse
(e.g. `report_coupon_not_applied(code=CASA50)`).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

Call = tuple[str, str, dict[str, Any]]
Probe = tuple[str, str, str, str, list[Call]]


def _in(db: dict[str, Any], days: int) -> str:
    return (date.fromisoformat(db["reference_date"]) + timedelta(days=days)).isoformat()


def _order_archetype(db: dict[str, Any], o: dict[str, Any]) -> str:
    pay = next(p for p in db["payments"] if p["id"] == o["payment_id"])
    ship = next((s["status"] for s in db["shipments"] if s["id"] == o["shipment_id"]), "-")
    tags = [o["status"], ship, pay["method"], o["items"][0]["category"]]
    if any(m["order_id"] == o["id"] for m in db["marketplace_orders"]):
        tags.append("marketplace")
    billing = next(b for b in db["billing_profiles"] if b["customer_id"] == o["customer_id"])
    tags.append(billing["doc_type"])
    return "/".join(tags)


def entity_probes(db: dict[str, Any]) -> list[Probe]:
    probes: list[Probe] = []
    coupons = [c["code"] for c in db["coupons"]]
    for o in db["orders"]:
        oid = {"order_id": o["id"]}
        calls: list[Call] = [
            (t, t, dict(oid))
            for t in (
                "check_extended_warranty",
                "get_seller_info",
                "track_seller_shipment",
                "get_invoice",
                "resend_invoice",
                "issue_return_invoice",
                "get_purchase_receipt",
                "request_price_protection",
                "claim_missing_points",
                "get_cashback_status",
            )
        ]
        calls += [
            ("schedule_installation", "schedule_installation", {**oid, "date": _in(db, 3)}),
            (
                "request_technical_visit",
                "request_technical_visit",
                {**oid, "date": _in(db, 3), "problem_description": "parou de funcionar"},
            ),
            ("contact_seller", "contact_seller", {**oid, "message": "Quando vocês enviam?"}),
            (
                "open_seller_mediation",
                "open_seller_mediation",
                {**oid, "reason": "produto_diferente"},
            ),
            (
                "report_seller_issue",
                "report_seller_issue",
                {**oid, "issue_type": "outro", "details": "anúncio confuso"},
            ),
            ("rate_seller", "rate_seller", {**oid, "rating": 5}),
            (
                "request_invoice_correction",
                "request_invoice_correction",
                {**oid, "field": "nome", "correct_value": "Nome Correto"},
            ),
        ]
        calls += [
            (
                f"report_coupon_not_applied(code={c})",
                "report_coupon_not_applied",
                {**oid, "code": c},
            )
            for c in coupons
        ]
        probes.append(("order", o["id"], o["customer_id"], _order_archetype(db, o), calls))

    for s in db["subscriptions"]:
        sid = {"subscription_id": s["id"]}
        probes.append(
            (
                "subscription",
                s["id"],
                s["customer_id"],
                f"{s['status']}/{s['payment_method']}",
                [
                    ("get_subscription", "get_subscription", dict(sid)),
                    ("pause_subscription", "pause_subscription", {**sid, "cycles": 1}),
                    ("cancel_subscription", "cancel_subscription", dict(sid)),
                    (
                        "change_subscription_date",
                        "change_subscription_date",
                        {**sid, "new_date": _in(db, 5)},
                    ),
                    (
                        "change_subscription_items",
                        "change_subscription_items",
                        {**sid, "sku": "CAF-GRAO-1K", "quantity": 1},
                    ),
                    (
                        "update_subscription_payment",
                        "update_subscription_payment",
                        {**sid, "method": "pix"},
                    ),
                ],
            )
        )

    for s in db["service_orders"]:
        sid = {"service_order_id": s["id"]}
        probes.append(
            (
                "service_order",
                s["id"],
                s["customer_id"],
                f"{s['type']}/{s['status']}",
                [
                    ("get_service_order_status", "get_service_order_status", dict(sid)),
                    (
                        "reschedule_technical_visit",
                        "reschedule_technical_visit",
                        {**sid, "new_date": _in(db, 4)},
                    ),
                    ("cancel_service_order", "cancel_service_order", dict(sid)),
                ],
            )
        )

    cards = {c["customer_id"]: c for c in db["store_cards"]}
    for c in db["customers"]:
        card = cards.get(c["id"])
        limit = card["limit"]["amount"] + 500 if card else 1000.0
        loyalty = next(a for a in db["loyalty_accounts"] if a["customer_id"] == c["id"])
        doc = next(b for b in db["billing_profiles"] if b["customer_id"] == c["id"])["doc_type"]
        arch = f"{loyalty['tier']}/{doc}/" + (
            f"card_{card['status']}_{card['bill']['status']}" if card else "no_card"
        )
        probes.append(
            (
                "customer",
                c["id"],
                c["id"],
                arch,
                [
                    ("get_points_balance", "get_points_balance", {}),
                    ("get_points_statement", "get_points_statement", {}),
                    ("redeem_points(points=500)", "redeem_points", {"points": 500}),
                    ("get_loyalty_tier", "get_loyalty_tier", {}),
                    ("get_gift_card_balance", "get_gift_card_balance", {}),
                    ("get_card_bill", "get_card_bill", {}),
                    ("generate_card_bill_copy", "generate_card_bill_copy", {}),
                    (
                        "request_limit_increase",
                        "request_limit_increase",
                        {"desired_limit": limit},
                    ),
                    ("block_store_card", "block_store_card", {"reason": "perda"}),
                    ("renegotiate_debt", "renegotiate_debt", {"installments": 6}),
                    (
                        "update_billing_data",
                        "update_billing_data",
                        {"field": "endereco_cobranca", "new_value": "Rua Nova, 100"},
                    ),
                    (
                        "update_contact_info",
                        "update_contact_info",
                        {"email": "novo.email@example.com"},
                    ),
                ],
            )
        )
        for tx in card["bill"]["transactions"] if card else []:
            probes.append(
                (
                    "card_transaction",
                    tx["id"],
                    c["id"],
                    "contested" if tx["contested"] else "normal",
                    [
                        (
                            "contest_card_transaction",
                            "contest_card_transaction",
                            {"transaction_id": tx["id"], "reason": "nao_reconhecida"},
                        )
                    ],
                )
            )

    for code in coupons:
        probes.append(
            (
                "coupon",
                code,
                "C001",
                "coupon",
                [("validate_coupon", "validate_coupon", {"code": code})],
            )
        )
    for p in db["promotions"]:
        probes.append(
            (
                "promotion",
                p["id"],
                "C001",
                "promotion",
                [("get_promotion_terms", "get_promotion_terms", {"promotion": p["id"]})],
            )
        )
    for g in db["gift_cards"]:
        owner = g["customer_id"] or "C001"
        probes.append(
            (
                "gift_card",
                g["code"],
                owner,
                g["status"],
                [
                    ("redeem_gift_card", "redeem_gift_card", {"code": g["code"]}),
                    ("get_gift_card_balance", "get_gift_card_balance", {"code": g["code"]}),
                ],
            )
        )
    for p in db["protocols"]:
        probes.append(
            (
                "protocol",
                p["id"],
                p["customer_id"],
                f"{p['kind']}/{p['status']}",
                [("check_protocol_status", "check_protocol_status", {"protocol": p["id"]})],
            )
        )
    return probes
