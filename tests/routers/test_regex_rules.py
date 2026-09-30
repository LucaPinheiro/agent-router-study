"""Phrase-level checks for config/regex_rules.yaml (phrases written from the catalog, not data)."""

from __future__ import annotations

import pytest

from routing_study.routers.base import RouteOption
from routing_study.routers.regex import RegexRouter

ROUTER = RegexRouter.from_path("config/regex_rules.yaml")
SKILLS = ["pedidos_logistica", "pagamentos_reembolsos", "trocas_devolucoes", "__global__"]


def _top(message: str, ids: list[str]) -> str | None:
    scores = ROUTER.score(message, [RouteOption(id=i, description=i) for i in ids])
    best = max(scores.values())
    winners = [k for k, v in scores.items() if v == best]
    return winners[0] if best > 0 and len(winners) == 1 else None


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
def test_skill_and_tool_phrases(message: str, skill: str, tool: str) -> None:
    assert _top(message, SKILLS) == skill
    tools = [
        "get_order_status",
        "track_shipment",
        "update_delivery_address",
        "reschedule_delivery",
        "cancel_order",
    ]
    assert _top(message, tools) == tool


def test_eligibility_hint_matches_at_end_of_message() -> None:
    tools = [
        "check_return_eligibility",
        "create_return_request",
        "generate_return_label",
        "create_exchange",
        "open_warranty_claim",
    ]
    assert _top("Ainda estou dentro do prazo?", tools) == "check_return_eligibility"
