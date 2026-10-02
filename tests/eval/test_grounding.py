"""Grounding (A7) gaps from final-code.md finding 10: parametrized cases."""

from __future__ import annotations

import pytest

from routing_study.eval.grounding import answer_facts, grounded
from routing_study.eval.scorers import score_turn

PROFILE = {"customer_id": "C001", "orders": [{"order_id": "O0009", "total": {"amount": 99.9}}]}


@pytest.mark.parametrize(
    ("answer", "ok"),
    [
        ("Seu pedido O0009 foi enviado.", True),
        ("Seu pedido o0009 foi enviado.", True),  # lower-case id is the same id
        ("Seu pedido o0010 foi enviado.", False),  # and an invented one is still caught
        ("Cliente c001, tudo certo.", True),
        ("Cliente c002, tudo certo.", False),
    ],
)
def test_f10_order_and_customer_ids_are_case_insensitive(answer: str, ok: bool) -> None:
    assert grounded(answer, [PROFILE])[0] is ok


@pytest.mark.parametrize(
    "text",
    ["1/12 pago", "parcela 1/12 paga", "3/10 pagas", "parcela 3/10", "3/10x", "2/12 parcelas"],
)
def test_f10_installment_fractions_are_not_dates(text: str) -> None:
    assert not {f for f in answer_facts(text) if f[0].startswith("date")}, text


@pytest.mark.parametrize(
    ("text", "fact"),
    [("entrega em 03/10", ("date_md", "10-03")), ("dia 5/11/2026", ("date", "2026-11-05"))],
)
def test_f10_real_dates_still_parse(text: str, fact: tuple[str, str]) -> None:
    assert fact in answer_facts(text)


@pytest.mark.parametrize(
    ("user", "ok"),
    [
        ("quero saber do pedido O0123", True),  # the id the user typed is evidence
        ("quero saber do pedido o0123", True),
        ("quero saber do meu pedido", False),
    ],
)
def test_f10_user_turns_are_evidence(user: str, ok: bool) -> None:
    rec = {
        "native": True,
        "mode": "e2e",
        "calls": [],
        "outcome": "answered",
        "final_answer": "Não encontrei o pedido O0123 na sua conta.",
        "customer": PROFILE,
        "skill": None,
        "tool": None,
    }
    exp = {"acceptable_skills": ["__abstain__"], "acceptable_tools": ["__abstain__"], "args": {}}
    turns = [{"role": "user", "content": user}]
    assert score_turn(rec, exp, {}, turns=turns)["grounded"] == float(ok)
