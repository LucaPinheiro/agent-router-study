"""Generate mcp_server/src/mcp_server/mock_db_large.json deterministically (large profile).

Run: uv run python mcp_server/scripts/generate_mock_db_large.py

The large DB is the small DB (`mock_db.json`, same customers, orders, payments, shipments,
refunds and returns, copied byte for byte as data) plus the entities of the 7 new skills and
the new globals: technical service orders and extended warranties, marketplace sellers and
seller-fulfilled orders, subscriptions, invoices and billing profiles, coupons / promotions /
current prices / gift cards, loyalty accounts / points statements / cashback, store cards, and
the customer's open protocols. Every state is chosen by an explicit table below (no RNG), so
re-running gives byte-identical files.

After writing the JSON it imports the large profile and calls every tool on every entity it
can take (canonical arguments) to write `mcp_server/MOCK_DB_NOTES_LARGE.md`: archetype per
entity and its `compatible_tools` (the tools that complete on it). The dataset generator (T4.1)
reads these notes to offer only slots whose target tool can complete.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "mcp_server"
BASE = PKG / "mock_db.json"
OUT = PKG / "mock_db_large.json"
NOTES = ROOT / "MOCK_DB_NOTES_LARGE.md"
TODAY = date(2026, 9, 29)


def h(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def d(days_from_today: int) -> str:
    return (TODAY + timedelta(days=days_from_today)).isoformat()


def money(v: float) -> dict[str, Any]:
    return {"amount": round(v, 2), "currency": "BRL"}


def ident(prefix: str, *parts: object) -> str:
    return f"{prefix}-{h(prefix, *parts)[:8].upper()}"


# ---------------------------------------------------------------- tables (explicit states)

SELLERS = [
    ("S01", "Casa & Cia Utilidades", 4.7, 2140, 24, "active"),
    ("S02", "TechMais Eletrônicos", 4.1, 980, 48, "active"),
    ("S03", "Passo Certo Calçados", 4.5, 1530, 24, "active"),
    ("S04", "Moda Viva Store", 4.3, 760, 48, "active"),
    ("S05", "Aventura Outdoor", 4.8, 410, 24, "active"),
    ("S06", "Ponto Digital Importados", 2.9, 230, 72, "under_review"),
]
SELLER_BY_CATEGORY = {
    "casa": "S01",
    "eletrodomesticos": "S01",
    "eletronicos": "S02",
    "calcados": "S03",
    "vestuario": "S04",
    "acessorios": "S05",
}
# order -> (seller override or None, seller shipment status)
MARKETPLACE = {
    "O0002": (None, "delivered"),
    "O0008": (None, "delivered"),
    "O0013": (None, "delivered"),
    "O0019": (None, "delivered"),
    "O0024": (None, "delivered"),
    "O0026": (None, "in_transit"),
    "O0030": (None, "posted"),
    "O0035": (None, "delivered"),
    "O0042": (None, "out_for_delivery"),
    "O0043": ("S04", "awaiting_post"),
    "O0047": (None, "delivered"),
    "O0048": ("S06", "delivered"),
    "O0049": (None, "delivered"),
    "O0055": (None, "delivered"),
    "O0059": (None, "delivered"),
}
SELLER_CARRIERS = ["Mandaê", "Kangu", "Correios", "Jadlog"]
MEDIATIONS = {"O0035": ("produto_diferente", "em_analise", -2)}  # order -> (reason, status, opened)
RATED = {"O0019": 5}

# order -> (type, status, scheduled in days, period)
SERVICE_ORDERS = {
    "O0029": ("instalacao", "agendada", 3, "manha"),
    "O0016": ("visita_tecnica", "agendada", 5, "tarde"),
    "O0007": ("visita_tecnica", "concluida", -1, "manha"),
    "O0049": ("instalacao", "cancelada", 2, "tarde"),
    "O0032": ("visita_tecnica", "em_atendimento", 0, "comercial"),
}
# order -> (plan months beyond the 12-month legal warranty, status)
EXTENDED_WARRANTIES = {
    "O0014": (12, "ativa"),
    "O0029": (24, "ativa"),
    "O0048": (12, "ativa"),
    "O0058": (24, "ativa"),
    "O0004": (12, "ativa"),
    "O0025": (12, "aguardando_entrega"),
}

SUB_PRODUCTS = {
    "CAP-CAFE-50": ("Cápsulas de café espresso (50 un.)", 89.90),
    "CAF-GRAO-1K": ("Café em grãos 1 kg", 64.90),
    "FIL-AGUA-3": ("Refil de filtro de água (3 un.)", 79.90),
    "RAC-CAO-10": ("Ração para cães adultos 10 kg", 159.90),
    "SAB-LIQ-5L": ("Sabão líquido 5 L", 54.90),
    "FRA-G-80": ("Fraldas tamanho G (80 un.)", 119.90),
}
# customer -> [(plan name, [(sku, qty)], frequency days, status, next delivery in days, payment)]
SUBSCRIPTIONS = {
    "C001": [("Clube do Café", [("CAP-CAFE-50", 2)], 30, "active", 6, "credit_card")],
    "C003": [("Casa em Dia", [("SAB-LIQ-5L", 1), ("FIL-AGUA-3", 1)], 30, "active", 12, "pix")],
    "C005": [
        ("Clube do Café", [("CAF-GRAO-1K", 2)], 15, "active", 4, "credit_card"),
        ("Pet Feliz", [("RAC-CAO-10", 1)], 30, "paused", 40, "credit_card"),
    ],
    "C008": [("Clube do Café", [("CAP-CAFE-50", 1)], 30, "cancelled", None, "pix")],
    "C010": [("Bebê em Casa", [("FRA-G-80", 2)], 30, "active", 9, "pix")],
    "C012": [("Pet Feliz", [("RAC-CAO-10", 2)], 30, "paused", 25, "cartao_loja")],
    "C014": [("Casa em Dia", [("FIL-AGUA-3", 1)], 60, "active", 20, "credit_card")],
    "C017": [("Clube do Café", [("CAP-CAFE-50", 1), ("CAF-GRAO-1K", 1)], 30, "active", 2, "pix")],
    "C019": [("Pet Feliz", [("RAC-CAO-10", 1)], 30, "active", 15, "pix")],
    "C020": [("Bebê em Casa", [("FRA-G-80", 1)], 30, "cancelled", None, "cartao_loja")],
}

CNPJ_CUSTOMERS = {
    "C004": "Oliveira Comércio de Utilidades Ltda",
    "C011": "Lima Arquitetura e Interiores Ltda",
    "C016": "Pereira Serviços Digitais ME",
    "C020": "Carvalho Distribuidora Ltda",
}
INVOICED_STATUSES = ("shipped", "in_transit", "delivered")

COUPONS = [
    # code, kind, value, min order, category or None, valid from, valid until, first purchase
    ("BEMVINDO10", "percent", 10, 100.0, None, -400, 400, True),
    ("CASA50", "fixed", 50, 300.0, "casa", -14, 16, False),
    ("MODA20", "percent", 20, 150.0, "vestuario", -28, 1, False),
    ("TECH15", "percent", 15, 300.0, "eletronicos", -35, -19, False),
    ("FRETE0", "fixed", 19.90, 99.0, None, -10, 20, False),
    ("PRIMAVERA30", "fixed", 30, 200.0, None, -12, 22, False),
    ("CALCE40", "fixed", 40, 250.0, "calcados", -15, 15, False),
]
PROMOTIONS = [
    (
        "SEMANA-CASA",
        "Semana da Casa",
        -14,
        16,
        ["CASA50"],
        "R$ 50 de desconto em itens de casa a "
        "partir de R$ 300, uma vez por CPF/CNPJ; não cumulativo com outros cupons.",
    ),
    (
        "MODA-PRIMAVERA",
        "Moda Primavera",
        -28,
        1,
        ["MODA20"],
        "20% em vestuário a partir de "
        "R$ 150; vale para itens vendidos e entregues pela loja; não cumulativo.",
    ),
    (
        "CASHBACK-PIX",
        "Cashback Pix",
        -28,
        93,
        [],
        "2% de cashback em compras pagas com Pix, "
        "liberado 30 dias após a entrega; cancelado se a compra for devolvida ou cancelada.",
    ),
    (
        "PONTOS-EM-DOBRO",
        "Pontos em Dobro Eletrônicos",
        -9,
        6,
        [],
        "Pontos em dobro em "
        "eletrônicos vendidos pela loja; os pontos extras caem com o crédito normal da compra.",
    ),
    (
        "TECH-SET",
        "Tech Setembro",
        -35,
        -19,
        ["TECH15"],
        "15% em eletrônicos a partir de R$ 300; encerrada.",
    ),
]
CURRENT_PRICES = {  # current price of the SKUs whose price dropped
    "TEN-RUN-42": 349.90,
    "SMW-FIT-3": 799.00,
    "CAF-EXP-10": 599.90,
    "JAQ-JEANS-G": 199.90,
    "FON-BT-X2": 329.00,
}
# code -> (customer or None, status, value, balance, expires in days)
GIFT_CARDS = {
    "VALE-7Q2K91XA": ("C001", "active", 150.0, 150.0, 200),
    "VALE-M4T8C2ZB": ("C005", "active", 100.0, 37.5, 120),
    "VALE-P9D3H6WQ": ("C005", "used", 50.0, 0.0, 60),
    "VALE-R2F7J1KC": ("C009", "expired", 80.0, 80.0, -15),
    "VALE-X5N8B3LD": ("C014", "active", 250.0, 250.0, 300),
    "PRESENTE-4K7M2Q": (None, "unredeemed", 100.0, 100.0, 365),
    "PRESENTE-8H3T6W": (None, "unredeemed", 200.0, 200.0, 365),
    "PRESENTE-2B9X5R": (None, "unredeemed", 50.0, 50.0, -3),
}
TIERS = [("bronze", 0), ("prata", 1500), ("ouro", 4000), ("diamante", 9000)]
MISSING_POINTS = {"O0047", "O0048"}  # delivered orders past the credit window, never credited
POINTS_BASE = {  # customer -> (lifetime bonus points, redeemed points)
    f"C{i:03d}": (300 + (i * 733) % 5200, (i * 211) % 900) for i in range(1, 21)
}

# customer -> (status, limit, bill status, bill due in days, overdue days or None)
STORE_CARDS = {
    "C002": ("active", 2000.0, "open", 8, None),
    "C005": ("active", 1500.0, "closed", 3, None),
    "C009": ("active", 1200.0, "overdue", -12, 12),
    "C012": ("blocked", 1800.0, "paid", -2, None),
    "C015": ("active", 3000.0, "paid", -5, None),
    "C018": ("active", 2500.0, "closed", 5, None),
    "C020": ("active", 1000.0, "overdue", -45, 45),
}
CARD_TX = [
    ("Loja física Shopping Center Norte", 189.90),
    ("Compra online - utilidades", 312.40),
    ("Loja física Shopping Iguatemi", 74.90),
    ("Seguro Proteção Cartão", 12.90),
    ("Compra online - eletrônicos", 455.00),
    ("Anuidade parcelada 1/12", 9.90),
]
CONTESTED_TX = {"C018": 1}  # customer -> index of the transaction already contested

# customer -> [(prefix, subject, status, opened days ago, expected in days)]
PROTOCOLS = {
    "C001": [("ATD", "Dúvida sobre entrega do pedido O0002", "concluido", 9, -6)],
    "C003": [("ATD", "Reclamação sobre atendimento", "em_analise", 2, 1)],
    "C007": [("NFC", "Carta de correção da NF do pedido O0019 (endereço)", "concluido", 5, -1)],
    "C013": [("AJC", "Cupom CALCE40 não aplicado no pedido O0039", "em_analise", 3, 2)],
    "C017": [("ATD", "Solicitação de contato por telefone", "aberto", 1, 1)],
}


# ---------------------------------------------------------------- build


def build() -> dict[str, Any]:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    db: dict[str, Any] = dict(base)
    orders = {o["id"]: o for o in base["orders"]}
    payments = {p["id"]: p for p in base["payments"]}
    customers = {c["id"]: c for c in base["customers"]}

    def days_ago(iso: str) -> int:
        return (TODAY - date.fromisoformat(iso)).days

    # ---- marketplace
    db["sellers"] = [
        {
            "id": sid,
            "name": name,
            "cnpj_masked": f"{10 + i * 7:02d}.{h(sid)[:3]}.***/0001-**",
            "rating": rating,
            "ratings_count": count,
            "response_hours": hours,
            "status": status,
        }
        for i, (sid, name, rating, count, hours, status) in enumerate(SELLERS)
    ]
    db["marketplace_orders"] = []
    for oid, (seller, status) in MARKETPLACE.items():
        o = orders[oid]
        seller = seller or SELLER_BY_CATEGORY[o["items"][0]["category"]]
        posted_ago = days_ago(o["created_at"]) - 1
        events = []
        if status != "awaiting_post":
            events.append(
                {
                    "at": d(-posted_ago) + "T09:30:00-03:00",
                    "location": "Centro de distribuição do vendedor",
                    "description": "Pedido postado pelo vendedor",
                }
            )
        if status in ("in_transit", "out_for_delivery", "delivered"):
            events.append(
                {
                    "at": d(-posted_ago + 1) + "T16:00:00-03:00",
                    "location": f"{o['delivery_address']['city']}/{o['delivery_address']['state']}",
                    "description": "Objeto em trânsito",
                }
            )
        if status == "out_for_delivery":
            events.append(
                {
                    "at": d(0) + "T08:10:00-03:00",
                    "location": o["delivery_address"]["city"],
                    "description": "Saiu para entrega",
                }
            )
        if status == "delivered":
            events.append(
                {
                    "at": o["delivered_at"] + "T15:40:00-03:00",
                    "location": o["delivery_address"]["city"],
                    "description": "Entregue ao destinatário",
                }
            )
        db["marketplace_orders"].append(
            {
                "order_id": oid,
                "seller_id": seller,
                "seller_carrier": SELLER_CARRIERS[int(h(oid, "car"), 16) % len(SELLER_CARRIERS)],
                "seller_tracking_code": None
                if status == "awaiting_post"
                else f"MK{h(oid, 'mk')[:10].upper()}",
                "seller_shipment_status": status,
                "eta": o["delivered_at"] if status == "delivered" else d(3),
                "events": events,
                "rating": RATED.get(oid),
            }
        )

    # ---- service orders and extended warranties
    db["service_orders"] = []
    for oid, (kind, status, when, period) in SERVICE_ORDERS.items():
        o = orders[oid]
        db["service_orders"].append(
            {
                "id": ident("OS", oid),
                "customer_id": o["customer_id"],
                "order_id": oid,
                "sku": o["items"][0]["sku"],
                "type": kind,
                "status": status,
                "scheduled_for": d(when),
                "period": period,
                "technician": None if status == "cancelada" else "Técnico credenciado Assist+",
                "created_at": o["delivered_at"] or o["created_at"],
            }
        )
    db["extended_warranties"] = []
    for oid, (months, status) in EXTENDED_WARRANTIES.items():
        o = orders[oid]
        start = o["delivered_at"] or o["created_at"]
        legal_end = date.fromisoformat(start) + timedelta(days=365)
        db["extended_warranties"].append(
            {
                "id": ident("GE", oid),
                "customer_id": o["customer_id"],
                "order_id": oid,
                "sku": o["items"][0]["sku"],
                "plan_months": months,
                "status": status,
                "starts_at": legal_end.isoformat(),
                "valid_until": (legal_end + timedelta(days=30 * months)).isoformat(),
                "coverage": "defeitos de funcionamento, com visita técnica ou reparo em oficina",
            }
        )

    # ---- subscriptions
    db["subscriptions"] = []
    for cid, subs in SUBSCRIPTIONS.items():
        cards = [
            payments[orders[oid]["payment_id"]]["card_last4"]
            for oid in customers[cid]["order_ids"]
            if payments[orders[oid]["payment_id"]]["card_last4"]
        ]
        for k, (plan, items, freq, status, next_in, method) in enumerate(subs):
            sid = ident("ASS", cid, k)
            last4 = cards[0] if method == "credit_card" else None
            if method == "cartao_loja":
                last4 = str(1000 + int(h(cid, "storecard"), 16) % 9000)
            db["subscriptions"].append(
                {
                    "id": sid,
                    "customer_id": cid,
                    "plan_name": plan,
                    "items": [
                        {
                            "sku": sku,
                            "name": SUB_PRODUCTS[sku][0],
                            "quantity": qty,
                            "unit_price": money(SUB_PRODUCTS[sku][1]),
                        }
                        for sku, qty in items
                    ],
                    "frequency_days": freq,
                    "status": status,
                    "next_delivery": d(next_in) if next_in is not None else None,
                    "paused_until": d(next_in) if status == "paused" else None,
                    "cancelled_at": d(-20) if status == "cancelled" else None,
                    "payment_method": method,
                    "card_last4": last4,
                    "created_at": d(-200 - 17 * int(cid[1:])),
                }
            )

    # ---- invoices and billing profiles
    db["billing_profiles"] = []
    for cid, c in customers.items():
        cnpj = cid in CNPJ_CUSTOMERS
        db["billing_profiles"].append(
            {
                "customer_id": cid,
                "doc_type": "cnpj" if cnpj else "cpf",
                "doc_masked": f"{h(cid, 'doc')[:2]}.***.***/0001-**"
                if cnpj
                else f"***.{int(h(cid, 'doc'), 16) % 1000:03d}.***-**",
                "billing_name": CNPJ_CUSTOMERS.get(cid, c["name"]),
                "state_registration": f"{int(h(cid, 'ie'), 16) % 10**9:09d}" if cnpj else None,
                "billing_address": c["default_address"],
            }
        )
    db["invoices"] = []
    for o in base["orders"]:
        if o["status"] not in INVOICED_STATUSES:
            continue
        issued = d(-(days_ago(o["created_at"]) - 1)) if days_ago(o["created_at"]) else d(0)
        number = 100000 + int(o["id"][1:]) * 37
        db["invoices"].append(
            {
                "id": f"NF-{number}",
                "order_id": o["id"],
                "number": str(number),
                "series": "1",
                "issued_at": issued,
                "access_key": str(int(h(o["id"], "nfe"), 16))[:44].ljust(44, "0"),
                "amount": o["total"],
            }
        )

    # ---- promotions, coupons, prices, gift cards
    db["coupons"] = [
        {
            "code": code,
            "kind": kind,
            "value": value,
            "min_order": money(min_order),
            "category": cat,
            "valid_from": d(start),
            "valid_until": d(end),
            "first_purchase_only": first,
        }
        for code, kind, value, min_order, cat, start, end, first in COUPONS
    ]
    db["promotions"] = [
        {
            "id": pid,
            "name": name,
            "valid_from": d(start),
            "valid_until": d(end),
            "coupons": coupons,
            "terms": terms,
        }
        for pid, name, start, end, coupons, terms in PROMOTIONS
    ]
    db["current_prices"] = [{"sku": s, "price": money(p)} for s, p in CURRENT_PRICES.items()]
    db["gift_cards"] = [
        {
            "code": code,
            "customer_id": cid,
            "status": status,
            "value": money(value),
            "balance": money(balance),
            "expires_at": d(exp),
        }
        for code, (cid, status, value, balance, exp) in GIFT_CARDS.items()
    ]

    # ---- loyalty and cashback
    db["loyalty_accounts"] = []
    db["cashback"] = []
    for cid, c in customers.items():
        bonus, redeemed = POINTS_BASE[cid]
        statement = [
            {
                "date": c["member_since"],
                "description": "Bônus de cadastro e campanhas anteriores",
                "points": bonus,
                "order_id": None,
            }
        ]
        pending = 0
        for oid in c["order_ids"]:
            o = orders[oid]
            pts = int(o["total"]["amount"])
            if o["delivered_at"] and days_ago(o["delivered_at"]) > 7 and oid not in MISSING_POINTS:
                credit = d(-(days_ago(o["delivered_at"]) - 7))
                statement.append(
                    {"date": credit, "description": f"Compra {oid}", "points": pts, "order_id": oid}
                )
            elif o["delivered_at"] and days_ago(o["delivered_at"]) <= 7:
                pending += pts
        if redeemed:
            statement.append(
                {
                    "date": d(-40),
                    "description": "Resgate de vale-compra",
                    "points": -redeemed,
                    "order_id": None,
                }
            )
        balance = sum(e["points"] for e in statement)
        lifetime = sum(e["points"] for e in statement if e["points"] > 0)
        tier = [t for t, floor in TIERS if lifetime >= floor][-1]
        nxt = next(((t, floor) for t, floor in TIERS if floor > lifetime), None)
        db["loyalty_accounts"].append(
            {
                "customer_id": cid,
                "points": balance,
                "pending_points": pending,
                "lifetime_points": lifetime,
                "tier": tier,
                "next_tier": nxt[0] if nxt else None,
                "points_to_next_tier": nxt[1] - lifetime if nxt else 0,
                "expiring_points": min(balance, 120) if balance else 0,
                "expiring_at": d(45),
                "statement": sorted(statement, key=lambda e: e["date"]),
            }
        )
        for oid in c["order_ids"]:
            o, p = orders[oid], payments[orders[oid]["payment_id"]]
            if p["method"] != "pix":
                continue
            amount = round(o["total"]["amount"] * 0.02, 2)
            if o["status"] == "cancelled":
                status, release = "cancelado", None
            elif o["delivered_at"]:
                ago = days_ago(o["delivered_at"])
                status = "disponivel" if ago >= 30 else "pendente"
                release = d(30 - ago)
            else:
                status, release = "aguardando_entrega", None
            db["cashback"].append(
                {
                    "order_id": oid,
                    "customer_id": cid,
                    "promotion_id": "CASHBACK-PIX",
                    "amount": money(amount),
                    "status": status,
                    "release_at": release,
                }
            )

    # ---- store cards
    db["store_cards"] = []
    for cid, (status, limit, bill_status, due, overdue) in STORE_CARDS.items():
        txs = []
        n = 3 + int(h(cid, "ntx"), 16) % 3
        for k in range(n):
            desc, amount = CARD_TX[(int(cid[1:]) + k) % len(CARD_TX)]
            contested = CONTESTED_TX.get(cid) == k
            txs.append(
                {
                    "id": ident("TX", cid, k),
                    "date": d(-(4 + 6 * k)),
                    "description": desc,
                    "amount": money(amount),
                    "contested": contested,
                    "contest_protocol": ident("CCL", cid, k) if contested else None,
                }
            )
        total = round(sum(t["amount"]["amount"] for t in txs), 2)
        overdue_amount = round(total * (1 + 0.012 * overdue), 2) if overdue else 0.0
        used = 0.0 if bill_status == "paid" else total
        db["store_cards"].append(
            {
                "id": ident("CL", cid),
                "customer_id": cid,
                "last4": str(1000 + int(h(cid, "storecard"), 16) % 9000),
                "status": status,
                "limit": money(limit),
                "available": money(limit - used),
                "bill": {
                    "status": bill_status,
                    "due_date": d(due),
                    "amount": money(total),
                    "minimum_payment": money(round(total * 0.15, 2)),
                    "amount_due": money(0.0 if bill_status == "paid" else total),
                    "transactions": txs,
                },
                "overdue_days": overdue,
                "overdue_amount": money(overdue_amount),
                "blocked_reason": "perda" if status == "blocked" else None,
            }
        )

    # ---- open protocols (mediations, card contests and the PROTOCOLS table)
    db["protocols"] = []
    for oid, (reason, status, opened) in MEDIATIONS.items():
        o = orders[oid]
        db["protocols"].append(
            {
                "id": ident("MED", oid),
                "customer_id": o["customer_id"],
                "kind": "mediacao_vendedor",
                "subject": f"Mediação com o vendedor do pedido {oid} ({reason})",
                "order_id": oid,
                "status": status,
                "opened_at": d(opened),
                "expected_by": d(opened + 10),
            }
        )
    for card in db["store_cards"]:
        for tx in card["bill"]["transactions"]:
            if tx["contest_protocol"]:
                db["protocols"].append(
                    {
                        "id": tx["contest_protocol"],
                        "customer_id": card["customer_id"],
                        "kind": "contestacao_cartao_loja",
                        "subject": f"Contestação da transação {tx['id']} do cartão da loja",
                        "order_id": None,
                        "status": "em_analise",
                        "opened_at": d(-3),
                        "expected_by": d(27),
                    }
                )
    for cid, rows in PROTOCOLS.items():
        for k, (prefix, subject, status, opened, expected) in enumerate(rows):
            db["protocols"].append(
                {
                    "id": ident(prefix, cid, k),
                    "customer_id": cid,
                    "kind": {
                        "ATD": "atendimento",
                        "NFC": "correcao_nota_fiscal",
                        "AJC": "ajuste_cupom",
                    }[prefix],
                    "subject": subject,
                    "order_id": None,
                    "status": status,
                    "opened_at": d(-opened),
                    "expected_by": d(expected),
                }
            )
    db["protocols"].sort(key=lambda p: (p["customer_id"], p["id"]))
    return db


# ---------------------------------------------------------------- notes (live tool probe)


def probe(db: dict[str, Any]) -> list[tuple[str, str, str, str, list[str]]]:
    """(entity kind, entity id, customer, archetype, compatible tools): every new tool is called
    with canonical arguments on every entity of its kind, in process (large profile)."""
    os.environ["CATALOG_PROFILE"] = "large"
    from fastmcp import Client
    from mcp_server.core import CUSTOMER_META_KEY
    from mcp_server.large.probes import entity_probes
    from mcp_server.server import build_server

    server = build_server("large")

    async def run() -> list[tuple[str, str, str, str, list[str]]]:
        rows = []
        async with Client(server) as client:
            for kind, entity_id, cid, archetype, calls in entity_probes(db):
                ok = []
                for label, tool, args in calls:
                    r = await client.call_tool(
                        tool, args, meta={CUSTOMER_META_KEY: cid}, raise_on_error=False
                    )
                    if not r.is_error:
                        ok.append(label)
                rows.append((kind, entity_id, cid, archetype, sorted(set(ok))))
        return rows

    return asyncio.run(run())


def render_notes(rows: list[tuple[str, str, str, str, list[str]]]) -> str:
    out = [
        "# Mock DB notes, large profile (generated by "
        "`mcp_server/scripts/generate_mock_db_large.py`, do not edit)",
        "",
        "`mock_db_large.json` = the small DB (`mock_db.json`: customers, orders, payments, "
        "shipments, refunds, returns, unchanged; see `MOCK_DB_NOTES.md`) + the entities below.",
        "Ids follow the same contract: customer `C00k` owns `O(3k-2)..O(3k)`. Reference date "
        f"{TODAY.isoformat()}.",
        "",
        "`compatible_tools` is measured, not declared: the generator calls every tool of the "
        "entity's kind with canonical arguments (in process, `CATALOG_PROFILE=large`) and lists "
        "the ones that complete. The dataset generator must only offer an entity for a target "
        "tool listed here. The 18 original tools on orders: see `MOCK_DB_NOTES.md`.",
        "",
        "| kind | entity | customer | archetype | compatible_tools |",
        "| --- | --- | --- | --- | --- |",
    ]
    out += [
        f"| {kind} | {eid} | {cid} | {arch} | {', '.join(tools) or '-'} |"
        for kind, eid, cid, arch, tools in rows
    ]
    return "\n".join(out) + "\n"


def main() -> None:
    db = build()
    OUT.write_text(json.dumps(db, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rows = probe(db)
    NOTES.write_text(render_notes(rows), encoding="utf-8")
    print(
        f"wrote {OUT.name} ({sum(len(v) for v in db.values() if isinstance(v, list))} rows) "
        f"and {NOTES.name} ({len(rows)} entities)"
    )


if __name__ == "__main__":
    main()
