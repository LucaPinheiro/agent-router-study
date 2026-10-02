"""Phrase-level checks for config/regex_rules_l.yaml (large catalog, 62 tools / 10 skills).

Every phrase comes from the catalog (tool `_meta` examples) or is written from the SKILL.md
disambiguation rules (G1-G12 probes); none comes from a dataset file. Routing is checked as the
host runs it: skill stage over the 10 skills + `__global__`, then tool stage over the chosen
skill's tools + the 5 globals.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from routing_study.routers.base import GLOBAL_OPTION, RouteOption
from routing_study.routers.regex import RegexRouter

ROOT = Path(__file__).resolve().parents[2]
ROUTER = RegexRouter.from_path(ROOT / "config" / "regex_rules_l.yaml")
TOOLS = json.loads((ROOT / "mcp_server" / "tools_list_large.json").read_text(encoding="utf-8"))[
    "tools"
]


def _skill(tool: dict) -> str:
    s = tool["_meta"]["br.routingstudy/skill"]
    return GLOBAL_OPTION if s == "global" else s


SKILL_OF = {t["name"]: _skill(t) for t in TOOLS}
EXAMPLES = {t["name"]: list(t["_meta"]["br.routingstudy/examples"]) for t in TOOLS}
BY_SKILL: dict[str, list[str]] = defaultdict(list)
for _t in TOOLS:
    BY_SKILL[_skill(_t)].append(_t["name"])
GLOBALS = BY_SKILL[GLOBAL_OPTION]
SKILLS = [s for s in BY_SKILL if s != GLOBAL_OPTION] + [GLOBAL_OPTION]


def _top(message: str, ids: list[str]) -> str | None:
    scores = ROUTER.score(message, [RouteOption(id=i, description=i) for i in ids])
    best = max(scores.values())
    winners = [k for k, v in scores.items() if v == best]
    return winners[0] if best > 0 and len(winners) == 1 else None


def _tool_options(skill: str) -> list[str]:
    return [*(BY_SKILL[skill] if skill != GLOBAL_OPTION else []), *GLOBALS]


def _routes(message: str, tool: str) -> bool:
    skill = SKILL_OF[tool]
    return _top(message, SKILLS) == skill and _top(message, _tool_options(skill)) == tool


def test_catalog_shape_and_rule_keys() -> None:
    assert len(TOOLS) == 62 and len(SKILLS) == 11 and len(GLOBALS) == 5
    keys = set(ROUTER.rules.rules)
    assert keys == set(SKILLS) | set(SKILL_OF), sorted(keys ^ (set(SKILLS) | set(SKILL_OF)))


@pytest.mark.parametrize("tool", sorted(EXAMPLES))
def test_at_least_two_catalog_examples_route_to_their_tool(tool: str) -> None:
    hits = [m for m in EXAMPLES[tool] if _routes(m, tool)]
    assert len(hits) >= 2, f"{tool}: {len(hits)}/{len(EXAMPLES[tool])} examples route"


# ------------------------------------------------- phase-1 phrase tests on the large catalog


@pytest.mark.parametrize(
    ("message", "skill", "tool"),
    [
        ("Preciso reagendar", "pedidos_logistica", "reschedule_delivery"),
        ("Dá para remarcar?", "pedidos_logistica", "reschedule_delivery"),
        ("Dá pra reagendar a entrega?", "pedidos_logistica", "reschedule_delivery"),
        ("Quero mudar meu endereço", "pedidos_logistica", "update_delivery_address"),
        ("Posso alterar o meu endereço?", "pedidos_logistica", "update_delivery_address"),
    ],
)
def test_phase1_skill_and_tool_phrases(message: str, skill: str, tool: str) -> None:
    assert _top(message, SKILLS) == skill
    assert _top(message, BY_SKILL[skill]) == tool  # the phase-1 option set (no globals)
    assert _top(message, _tool_options(skill)) == tool  # the large tool stage (+ 5 globals)


def test_phase1_eligibility_hint_matches_at_end_of_message() -> None:
    message = "Ainda estou dentro do prazo?"
    assert _top(message, BY_SKILL["trocas_devolucoes"]) == "check_return_eligibility"
    assert _top(message, _tool_options("trocas_devolucoes")) == "check_return_eligibility"


# ------------------------------------------------- confusable groups (docs/catalog-large.md §2)

PROBES = {
    "G1": [
        ("Cobraram duas vezes no meu cartão de crédito", "dispute_charge"),
        ("Cobraram duas vezes na fatura do cartão da loja", "contest_card_transaction"),
        ("O vendedor parceiro me cobrou a mais", "open_seller_mediation"),
    ],
    "G2": [
        ("Preciso da segunda via do boleto do pedido", "generate_boleto_second_copy"),
        ("Preciso da segunda via da fatura do crediário", "generate_card_bill_copy"),
        ("Quanto veio a fatura do cartão da loja?", "get_card_bill"),
    ],
    "G3": [
        ("O estorno do pedido cancelado ainda não caiu", "get_refund_status"),
        ("O cashback ainda não caiu", "get_cashback_status"),
        ("Os pontos da compra não caíram", "claim_missing_points"),
    ],
    "G4": [
        ("Quero cancelar o pedido antes de enviarem", "cancel_order"),
        ("Quero cancelar a assinatura", "cancel_subscription"),
        ("Quero cancelar a visita do técnico", "cancel_service_order"),
    ],
    "G5": [
        ("Quero remarcar a entrega do pedido", "reschedule_delivery"),
        ("Quero mudar o dia da entrega da assinatura", "change_subscription_date"),
        ("Quero remarcar a visita técnica", "reschedule_technical_visit"),
    ],
    "G6": [
        ("Onde está meu pacote?", "track_shipment"),
        ("Onde está o pacote que o vendedor parceiro enviou?", "track_seller_shipment"),
    ],
    "G7": [
        ("Meu fone deu defeito depois de 4 meses", "open_warranty_claim"),
        ("A geladeira deu defeito, quero um técnico em casa", "request_technical_visit"),
        ("Meu produto tem garantia estendida?", "check_extended_warranty"),
    ],
    "G8": [
        ("Quero mudar o endereço de entrega do pedido", "update_delivery_address"),
        ("Quero mudar o endereço de cobrança das notas", "update_billing_data"),
        ("Quero mudar meu e-mail", "update_contact_info"),
    ],
    "G9": [
        ("O preço baixou depois que comprei", "request_price_protection"),
        ("Meu pedido foi extraviado, quero meu dinheiro de volta", "request_refund"),
    ],
    "G10": [
        ("Quero devolver o produto que recebi", "create_return_request"),
        ("Comprei com CNPJ e preciso da nota de devolução", "issue_return_invoice"),
        ("O vendedor parceiro recusou a devolução", "open_seller_mediation"),
    ],
    "G11": [
        ("O pagamento do pedido já foi aprovado?", "get_payment_status"),
        ("Preciso do comprovante de pagamento", "get_purchase_receipt"),
        ("Preciso da nota fiscal do pedido", "get_invoice"),
    ],
    "G12": [
        ("Esse cupom ainda vale?", "validate_coupon"),
        ("O cupom não foi aplicado na minha compra", "report_coupon_not_applied"),
        ("Quero ativar um vale-presente que ganhei", "redeem_gift_card"),
    ],
}


@pytest.mark.parametrize(
    ("group", "message", "tool"),
    [(g, m, t) for g, cases in PROBES.items() for m, t in cases],
    ids=[f"{g}-{t}" for g, cases in PROBES.items() for _, t in cases],
)
def test_confusable_group_probe(group: str, message: str, tool: str) -> None:
    assert _routes(message, tool), (group, message, tool)
