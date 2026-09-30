"""Generate mcp_server/src/mcp_server/mock_db.json deterministically (seed 42).

Run: uv run python mcp_server/scripts/generate_mock_db.py
Order ids and ownership follow the labeled dataset (data/README.md); each order's state is
chosen so that the dataset cases referencing it can complete their expected tool. Also writes
mcp_server/MOCK_DB_NOTES.md (state per order and unresolved conflicts).
The outputs are versioned; re-running must produce byte-identical files.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path

TODAY = date(2026, 9, 29)
OUT = Path(__file__).resolve().parents[1] / "src" / "mcp_server" / "mock_db.json"
NOTES = Path(__file__).resolve().parents[1] / "MOCK_DB_NOTES.md"

FIRST = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabriela", "Heitor", "Isabela",
         "João", "Karina", "Lucas", "Mariana", "Nicolas", "Olívia", "Paulo", "Renata", "Samuel",
         "Tatiana", "Vinícius"]
LAST = ["Silva", "Souza", "Oliveira", "Santos", "Pereira", "Lima", "Costa", "Ribeiro",
        "Almeida", "Carvalho"]
CITIES = [("São Paulo", "SP", "01"), ("Rio de Janeiro", "RJ", "20"), ("Belo Horizonte", "MG", "30"),
          ("Curitiba", "PR", "80"), ("Porto Alegre", "RS", "90"), ("Recife", "PE", "50"),
          ("Salvador", "BA", "40"), ("Fortaleza", "CE", "60")]
STREETS = ["Rua das Flores", "Avenida Brasil", "Rua XV de Novembro", "Rua da Consolação",
           "Avenida Paulista", "Rua Augusta", "Rua dos Andradas", "Avenida Atlântica"]
HOODS = ["Centro", "Jardim América", "Vila Nova", "Boa Vista", "Santa Cecília", "Moinhos"]
PRODUCTS = [
    ("TEN-RUN-42", "Tênis de corrida Veloz tam. 42", 399.90, "calcados"),
    ("TEN-CASUAL-39", "Tênis casual Urbano tam. 39", 259.90, "calcados"),
    ("CAM-BAS-M", "Camiseta básica algodão M", 59.90, "vestuario"),
    ("JAQ-JEANS-G", "Jaqueta jeans G", 229.90, "vestuario"),
    ("VES-MIDI-P", "Vestido midi P", 189.90, "vestuario"),
    ("FON-BT-X2", "Fone Bluetooth X2", 349.00, "eletronicos"),
    ("SMW-FIT-3", "Smartwatch Fit 3", 899.00, "eletronicos"),
    ("CAF-EXP-10", "Cafeteira expresso 10 bar", 649.90, "eletrodomesticos"),
    ("LIQ-PRO-900", "Liquidificador Pro 900W", 279.90, "eletrodomesticos"),
    ("MOC-TRIP-40", "Mochila trilha 40L", 319.90, "acessorios"),
    ("GAR-TERM-1L", "Garrafa térmica 1L", 119.90, "acessorios"),
    ("PAN-ANTI-5", "Jogo de panelas antiaderente 5 peças", 499.90, "casa"),
]
CARRIERS = ["Correios", "Loggi", "Jadlog", "Total Express"]

DATA = Path(__file__).resolve().parents[2] / "data"
DATASETS = ("dataset_dev.jsonl", "dataset_test.jsonl", "seed.jsonl")
ORDERS_PER_CUSTOMER = 3  # dataset contract: C00k owns O(3k-2)..O(3k) (data/README.md)
ORDER_ID_RE = re.compile(r"\bO\d{4}\b")
ALWAYS_OK = {"get_order_status", "get_payment_status", "get_customer_profile",
             "search_help_center", "escalate_to_human", "__abstain__"}

# name: (order status, shipment status | None, payment method, payment status,
#        delivered days-ago range | None, has refund, has open return)
ARCHETYPES: dict[str, tuple] = {
    "awaiting_boleto": ("awaiting_payment", None, "boleto", "pending", None, False, False),
    "processing_card": ("processing", None, "credit_card", "approved", None, False, False),
    "processing_pix": ("processing", None, "pix", "approved", None, False, False),
    "processing_boleto": ("processing", None, "boleto", "approved", None, False, False),
    "shipped_card": ("shipped", "label_created", "credit_card", "approved", None, False, False),
    "in_transit_card": ("in_transit", "in_transit", "credit_card", "approved", None, False,
                        False),
    "in_transit_pix": ("in_transit", "out_for_delivery", "pix", "approved", None, False, False),
    "failed_delivery_boleto": ("in_transit", "delivery_failed", "boleto", "approved", None,
                               False, False),
    "failed_delivery_card": ("in_transit", "delivery_failed", "credit_card", "approved", None,
                             False, False),
    "lost_card": ("in_transit", "lost", "credit_card", "approved", None, False, False),
    "lost_pix": ("in_transit", "lost", "pix", "approved", None, False, False),
    "lost_refunded": ("in_transit", "lost", "credit_card", "refunded", None, True, False),
    "delivered_recent_card": ("delivered", "delivered", "credit_card", "approved", (2, 6),
                              False, False),
    "delivered_recent_pix": ("delivered", "delivered", "pix", "approved", (2, 6), False, False),
    "delivered_recent_return": ("delivered", "delivered", "credit_card", "approved", (3, 6),
                                False, True),
    "delivered_recent_return_refund": ("delivered", "delivered", "credit_card", "approved",
                                       (4, 6), True, True),
    "delivered_mid_boleto": ("delivered", "delivered", "boleto", "approved", (10, 25), False,
                             False),
    "delivered_old_card": ("delivered", "delivered", "credit_card", "approved", (45, 80), False,
                           False),
    "delivered_old_pix": ("delivered", "delivered", "pix", "approved", (45, 80), False, False),
    "delivered_ancient_card": ("delivered", "delivered", "credit_card", "approved", (400, 420),
                               False, False),
    "delivered_chargeback": ("delivered", "delivered", "credit_card", "chargeback", (35, 45),
                             False, False),
    "cancelled_refunded_card": ("cancelled", None, "credit_card", "refunded", None, True, False),
    "cancelled_refunded_pix": ("cancelled", None, "pix", "refunded", None, True, False),
    "cancelled_unrefunded_card": ("cancelled", None, "credit_card", "approved", None, False,
                                  False),
    "cancelled_unrefunded_pix": ("cancelled", None, "pix", "approved", None, False, False),
}


def compatible_tools(arch: tuple) -> set[str]:
    """Tools that complete (no business error) for an order in this archetype, given an
    order_id. Mirrors the rules in mcp_server/tools/*; delivered orders have one item so sku
    is never needed. `delivered` range upper bound is the worst case."""
    status, ship, method, pay, delivered, refund, ret = arch
    ok = set(ALWAYS_OK)
    if ship:
        ok.add("track_shipment")
    if ship and ship not in ("delivered", "lost"):
        ok.add("reschedule_delivery")
    if status in ("awaiting_payment", "processing"):
        ok |= {"cancel_order", "update_delivery_address"}
    if method == "boleto" and pay == "pending":
        ok.add("generate_boleto_second_copy")
    if not refund and pay == "approved" and (status == "cancelled" or ship == "lost"):
        ok.add("request_refund")
    if refund:
        ok.add("get_refund_status")
    paid_max = (delivered[1] + 8) if delivered else 9
    if method == "credit_card" and pay == "approved" and paid_max <= 90:
        ok.add("dispute_charge")
    if delivered:
        lo, hi = delivered
        ok.add("check_return_eligibility")
        if ret:
            ok.add("generate_return_label")
        elif hi <= 7:
            ok.add("create_return_request")
        if hi <= 30:
            ok.add("create_exchange")
        if 30 < lo and hi <= 365:
            ok.add("open_warranty_claim")
    return ok


def load_cases() -> list[dict]:
    cases: dict[str, dict] = {}
    for name in DATASETS:
        for line in (DATA / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                cases[row["id"]] = row
    return [cases[k] for k in sorted(cases)]


def order_demands(cases: list[dict]) -> dict[str, list[tuple[float, list[str], str]]]:
    """order id -> [(weight, acceptable_tools, case id)]. Weight 1 when the order is the
    expected order_id arg, 0.5 when only mentioned in the conversation."""
    demands: dict[str, list[tuple[float, list[str], str]]] = {}
    for c in cases:
        arg = c["expected"]["args"].get("order_id")
        ids = set(ORDER_ID_RE.findall(" ".join(t["content"] for t in c["turns"])))
        if arg:
            ids.add(arg)
        for oid in sorted(ids):
            weight = 1.0 if oid == arg else 0.5
            demands.setdefault(oid, []).append(
                (weight, c["expected"]["acceptable_tools"], c["id"]))
    return demands


def case_score(tools: list[str], ok: set[str]) -> float:
    """1 if the first acceptable tool completes, 0.5 if only an alternative does."""
    if tools[0] in ok:
        return 1.0
    return 0.5 if any(t in ok for t in tools) else 0.0


def choose_archetypes(order_ids: list[str], demands: dict, rng: random.Random) -> dict[str, str]:
    compat = {name: compatible_tools(a) for name, a in ARCHETYPES.items()}
    chosen: dict[str, str] = {}
    used = dict.fromkeys(ARCHETYPES, 0)
    for oid in order_ids:
        scores = {name: sum(w * case_score(tools, ok) for w, tools, _ in demands.get(oid, []))
                  for name, ok in compat.items()}
        best = max(scores.values())
        tied = [n for n, s in scores.items() if s == best]
        least = min(used[n] for n in tied)  # ties favour unused archetypes (state coverage)
        chosen[oid] = rng.choice(sorted(n for n in tied if used[n] == least))
        used[chosen[oid]] += 1
    return chosen


def h(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def d(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


def ev(days_ago: int, time: str, location: str, description: str) -> dict:
    return {"at": d(days_ago) + time, "location": location, "description": description}


def money(v: float) -> dict:
    return {"amount": round(v, 2), "currency": "BRL"}


def main() -> None:
    rng = random.Random(42)
    cases = load_cases()
    demands = order_demands(cases)
    all_ids = [f"O{i:04d}" for i in range(1, 20 * ORDERS_PER_CUSTOMER + 1)]
    chosen = choose_archetypes(all_ids, demands, random.Random(7))
    db: dict = {"reference_date": TODAY.isoformat(), "customers": [], "orders": [],
                "payments": [], "shipments": [], "refunds": [], "returns": []}
    for ci in range(20):
        cid = f"C{ci + 1:03d}"
        first, last = FIRST[ci], LAST[ci % len(LAST)]
        city, uf, cep_prefix = CITIES[ci % len(CITIES)]
        address = {
            "street": STREETS[ci % len(STREETS)], "number": str(rng.randint(10, 2500)),
            "complement": rng.choice([None, "Apto 12", "Casa 2", "Bloco B"]),
            "neighborhood": HOODS[ci % len(HOODS)], "city": city, "state": uf,
            "postal_code": f"{cep_prefix}{rng.randint(100, 999)}{rng.randint(100, 999)}",
        }
        email_user = first.lower().translate(str.maketrans("áéíóúç", "aeiouc"))
        customer = {
            "id": cid, "name": f"{first} {last}",
            "email": f"{email_user}.{last.lower()}@example.com",
            "tier": rng.choice(["standard", "standard", "gold", "platinum"]),
            "member_since": d(rng.randint(400, 2000)), "default_address": address, "order_ids": [],
        }
        for k in range(ORDERS_PER_CUSTOMER):
            oid = all_ids[ci * ORDERS_PER_CUSTOMER + k]
            status, ship_status, method, pay_status, window, has_refund, has_return = (
                ARCHETYPES[chosen[oid]])
            delivered_ago = rng.randint(*window) if window else None
            n_items = 1 if delivered_ago is not None else rng.choice([1, 1, 2])
            picks = rng.sample(PRODUCTS, n_items)
            items = [{"sku": p[0], "name": p[1], "quantity": 1, "unit_price": money(p[2]),
                      "category": p[3]} for p in picks]
            total = sum(p[2] for p in picks)
            if delivered_ago is not None:
                created_ago = delivered_ago + rng.randint(3, 8)
            elif status in ("awaiting_payment", "processing"):
                created_ago = rng.randint(0, 2)
            else:
                created_ago = rng.randint(3, 9)
            pid = f"PAY-{h(oid, 'pay')[:8].upper()}"
            order = {
                "id": oid, "customer_id": cid, "created_at": d(created_ago), "status": status,
                "items": items, "total": money(total), "payment_id": pid,
                "delivery_address": address, "shipment_id": None,
                "estimated_delivery": None, "delivered_at": None, "cancelled_at": None,
            }
            installments = rng.choice([1, 2, 3, 6, 10]) if method == "credit_card" else 1
            payment = {
                "id": pid, "order_id": oid, "method": method, "status": pay_status,
                "amount": money(total), "installments": installments,
                "paid_at": None if pay_status == "pending" else d(created_ago),
                "card_last4": str(rng.randint(1000, 9999)) if method == "credit_card" else None,
                "boleto_due_date": None, "boleto_barcode": None,
            }
            if method == "boleto":
                due_ago = created_ago - 3
                payment["boleto_due_date"] = d(due_ago)
                digits = str(int(h(oid, "boleto"), 16))[:47].ljust(47, "0")
                payment["boleto_barcode"] = digits
            if status == "cancelled":
                order["cancelled_at"] = d(max(created_ago - 1, 0))
            if status in ("awaiting_payment", "processing"):
                order["estimated_delivery"] = d(-rng.randint(5, 10))
            if ship_status:
                sid = f"SHP-{h(oid, 'ship')[:8].upper()}"
                order["shipment_id"] = sid
                carrier = CARRIERS[rng.randint(0, len(CARRIERS) - 1)]
                hub = "Centro de distribuição Cajamar/SP"
                events = [ev(created_ago - 1, "T10:00:00-03:00", hub,
                             "Etiqueta criada e pedido despachado")]
                eta = d(-rng.randint(1, 5))
                if ship_status in ("in_transit", "out_for_delivery", "delivery_failed", "lost",
                                   "delivered"):
                    events.append(ev(created_ago - 2, "T08:30:00-03:00",
                                     f"Unidade de tratamento {city}/{uf}", "Objeto em trânsito"))
                if ship_status == "out_for_delivery":
                    events.append(ev(0, "T07:45:00-03:00", f"{city}/{uf}",
                                     "Objeto saiu para entrega"))
                if ship_status == "delivery_failed":
                    events.append(ev(1, "T15:20:00-03:00", f"{city}/{uf}",
                                     "Tentativa de entrega sem sucesso: destinatário ausente"))
                if ship_status == "lost":
                    eta = d(6)
                    events.append(ev(2, "T11:00:00-03:00", f"Unidade de tratamento {city}/{uf}",
                                     "Objeto não localizado no fluxo postal (extraviado)"))
                if ship_status == "delivered":
                    order["delivered_at"] = d(delivered_ago)
                    eta = d(delivered_ago)
                    events.append(ev(delivered_ago, "T14:10:00-03:00", f"{city}/{uf}",
                                     "Objeto entregue ao destinatário"))
                order["estimated_delivery"] = eta
                db["shipments"].append({
                    "id": sid, "order_id": oid, "carrier": carrier,
                    "tracking_code": f"BR{h(oid, 'trk')[:9].upper()}BR", "status": ship_status,
                    "eta": eta, "events": events, "reschedules_used": 0,
                })
            if has_refund:
                db["refunds"].append({
                    "id": f"REF-{h(oid, 'ref')[:8].upper()}", "order_id": oid, "payment_id": pid,
                    "status": "processing", "amount": money(total), "method": method,
                    "requested_at": order["cancelled_at"] or d(1), "expected_by": d(-10),
                })
            if has_return:
                db["returns"].append({
                    "id": f"DEV-{h(oid, 'ret')[:8].upper()}", "order_id": oid,
                    "sku": items[0]["sku"], "reason": "arrependimento", "status": "approved",
                    "created_at": d(max(delivered_ago - 1, 1)), "post_by": d(-8),
                })
            db["orders"].append(order)
            db["payments"].append(payment)
            customer["order_ids"].append(oid)
        db["customers"].append(customer)
    OUT.write_text(json.dumps(db, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    NOTES.write_text(render_notes(all_ids, chosen, demands), encoding="utf-8")
    print(f"wrote {OUT} ({len(db['orders'])} orders) and {NOTES.name}")


def render_notes(order_ids: list[str], chosen: dict[str, str], demands: dict) -> str:
    compat = {name: compatible_tools(a) for name, a in ARCHETYPES.items()}
    rows, conflicts, partial = [], [], []
    total = satisfied = 0.0
    for oid in order_ids:
        ok = compat[chosen[oid]]
        ds = demands.get(oid, [])
        got = sum(w * case_score(tools, ok) for w, tools, _ in ds)
        want = sum(w for w, _, _ in ds)
        total, satisfied = total + want, satisfied + got
        rows.append(f"| {oid} | {chosen[oid]} | {len(ds)} | {got:g}/{want:g} |")
        for w, tools, case_id in ds:
            score = case_score(tools, ok)
            if score < 1:
                target = conflicts if score == 0 else partial
                kind = "arg" if w == 1 else "mention"
                target.append(f"| {case_id} | {oid} | {kind} | {', '.join(tools)} | "
                              f"{chosen[oid]} |")
    head = ("| case | order | order as | acceptable_tools | order archetype |\n"
            "| --- | --- | --- | --- | --- |")
    return "\n".join([
        "# Mock DB notes (generated by `mcp_server/scripts/generate_mock_db.py`, do not edit)",
        "",
        "Ids follow the dataset contract (`data/README.md`): customer `C00k` owns "
        "`O(3k-2)..O(3k)`.",
        "Each order gets the archetype (state) that lets the most dataset cases referencing it "
        "complete their expected tool (weight 1 when the order is `expected.args.order_id`, "
        "0.5 when only mentioned; 1 point if the first acceptable tool completes, 0.5 if only "
        "an alternative does). Ties are broken with `random.Random(7)`.",
        "Cases without `order_id` for a customer with 3 orders are expected to get "
        "`VALIDATION_ERROR` with `details.options` (the router should ask which order).",
        "",
        f"Weighted satisfaction: {satisfied:g}/{total:g} ({satisfied / total:.1%}).",
        "",
        "## Unresolved conflicts (no acceptable tool completes on the chosen state)",
        "",
        head, *conflicts, "",
        "## Partial (only a non-first acceptable tool completes)",
        "",
        head, *partial, "",
        "## Archetype per order",
        "",
        "| order | archetype | cases | weighted score |",
        "| --- | --- | --- | --- |",
        *rows, "",
    ])


if __name__ == "__main__":
    main()
