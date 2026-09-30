"""Confidence calibration, pt-BR text normalization and the tunable lexical-router options."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from router_helpers import skill_input

from routing_study.routers.base import Message, RouteOption, RoutingInput
from routing_study.routers.bm25 import BM25Router
from routing_study.routers.calibration import Calibration, ece, fit_isotonic
from routing_study.routers.common import stem_pt, tokenize
from routing_study.routers.regex import RegexRouter, RegexRules
from routing_study.settings import BM25Strategy, RegexStrategy

# ------------------------------------------------------------------ calibration


def test_isotonic_fit_is_monotone_with_beta_prior():
    cal = fit_isotonic([0.1, 0.2, 0.3, 0.8, 0.9, 0.95], [0, 1, 0, 1, 1, 1])
    assert cal.y == sorted(cal.y)
    # the violating pair (0.2 -> 1, 0.3 -> 0) is pooled into one block
    assert len(cal.x) == 3
    # all-correct top block of 3 maps to (3 + 1) / (3 + 2), never to 1.0
    assert cal.y[-1] == pytest.approx(0.8)
    assert cal(0.05) == pytest.approx(cal.y[0]) and cal(1.0) == pytest.approx(0.8)
    assert cal(0.0) == 0.0  # the "do not trust" sentinel stays 0


def test_isotonic_ties_share_a_block():
    cal = fit_isotonic([0.1, 0.5, 0.5], [1, 0, 1])
    assert 0.5 not in cal.x[1:] or len(cal.x) == 1  # 0.5 never split across two knots
    assert len(cal.x) == len(set(cal.x))


def test_calibration_interpolates_between_knots():
    cal = Calibration(x=[0.2, 0.6], y=[0.4, 0.8])
    assert cal(0.4) == pytest.approx(0.6)
    assert cal(0.1) == pytest.approx(0.4) and cal(0.9) == pytest.approx(0.8)  # flat outside


@pytest.mark.parametrize(
    ("x", "y"),
    [([0.1, 0.2], [0.5]), ([0.3, 0.1], [0.1, 0.2]), ([0.1, 0.2], [0.6, 0.5]), ([0.1], [1.2])],
)
def test_calibration_rejects_invalid_maps(x, y):
    with pytest.raises(ValidationError):
        Calibration(x=x, y=y)


def test_ece():
    assert ece([0.9, 0.9], [1, 1]) == pytest.approx(0.1)
    assert ece([0.25, 0.75], [0, 1]) == pytest.approx(0.25)
    assert ece([], []) == 0.0


def test_strategy_config_accepts_calibration_per_level():
    cfg = RegexStrategy.model_validate(
        {"calibration": {"skill": {"x": [0.0, 1.0], "y": [0.2, 0.9]}}}
    )
    assert cfg.calibration["skill"](1.0) == pytest.approx(0.9)
    with pytest.raises(ValidationError):
        BM25Strategy.model_validate({"calibration": {"stage": {"x": [0], "y": [0]}}})


async def test_router_applies_calibration_and_keeps_raw(skill_options):
    rules = RegexRules.model_validate({"rules": {"pedidos_logistica": [{"pattern": "encomenda"}]}})
    cal = {"skill": Calibration(x=[0.0, 1.0], y=[0.1, 0.7])}
    d = await RegexRouter(rules, cal).route(skill_input("cade a encomenda"), skill_options)
    assert d.confidence == pytest.approx(0.7)
    assert d.usage["raw_confidence"] == pytest.approx(1.0)
    tool = RoutingInput(message="cade a encomenda", level="tool")
    d = await RegexRouter(rules, cal).route(tool, skill_options)  # no tool map: raw
    assert d.confidence == pytest.approx(1.0) and "raw_confidence" not in d.usage
    d = await RegexRouter(rules, cal).route(skill_input("bom dia"), skill_options)
    assert d.choice is None and d.confidence == 0.0


# ------------------------------------------------------------------ text


@pytest.mark.parametrize(
    ("word", "stem"),
    [
        ("devolver", "devolv"),
        ("devolvido", "devolv"),
        ("reembolsos", "reembols"),
        ("reembolsar", "reembols"),
        ("cancelamento", "cancel"),
        ("pedidos", "ped"),
        ("sim", "sim"),
        ("0004", "0004"),
    ],
)
def test_light_stemmer(word, stem):
    assert stem_pt(word) == stem


def test_tokenize_options():
    text = "Bom dia, por favor: quero DEVOLVER o pedido O0004"
    assert tokenize(text) == ["bom", "dia", "favor", "devolver", "pedido", "o0004"]
    assert tokenize(text, stopwords="extended") == ["devolver", "pedido", "o0004"]
    assert tokenize(text, stemmer="prefix", prefix_len=4) == [
        "bom",
        "dia",
        "favo",
        "devo",
        "pedi",
        "o000",
    ]
    assert "devolv" in tokenize(text, stemmer="light")


# ------------------------------------------------------------------ bm25 options


OPTS = [
    RouteOption(id="a", description="devolver produto com defeito"),
    RouteOption(id="b", description="devolver dinheiro reembolso"),
    RouteOption(id="c", description="rastrear entrega"),
    RouteOption(id="d", description="cancelar pedido"),
]


def test_bm25l_keeps_idf_of_terms_in_half_the_documents():
    # "devolver" is in 2 of 4 documents: Okapi IDF = log(2.5 / 2.5) = 0
    assert BM25Router().scores("devolver", OPTS) == []
    ranked = BM25Router(variant="l").scores("devolver", OPTS)
    assert {k for k, v in ranked if v > 0} == {"a", "b"}


async def test_bm25_history_routes_a_short_follow_up():
    inp = RoutingInput(
        message="sim, faz isso",
        level="skill",
        history=[
            Message(role="user", content="quero rastrear a entrega"),
            Message(role="assistant", content="posso verificar"),
        ],
    )
    assert (await BM25Router().route(inp, OPTS)).choice is None
    d = await BM25Router(history_turns=2).route(inp, OPTS)
    assert d.choice == "c"


def test_bm25_field_repeats_zero_drops_the_field():
    opts = [
        RouteOption(id="a", description="x", keywords=["boleto"]),
        RouteOption(id="b", description="y", examples=["pix"]),
    ]
    assert BM25Router(variant="l").scores("boleto", opts)[0][0] == "a"
    assert BM25Router(variant="l", field_repeats={"keywords": 0}).scores("boleto", opts) == []


# ------------------------------------------------------------------ regex options


def test_regex_defs_expand_and_suppressors_subtract():
    rules = RegexRules.model_validate(
        {
            "defs": {"MONEY": "dinheiro|grana", "BACK": "{{MONEY}} de volta"},
            "rules": {
                "refund": [{"pattern": r"\b{{BACK}}"}],
                "policy": [
                    {"pattern": r"\bpolitica\b"},
                    {"pattern": r"\bo\d{4}\b", "weight": -0.6},
                ],
            },
        }
    )
    assert rules.rules["refund"][0].pattern == r"\b(?:(?:dinheiro|grana) de volta)"
    router = RegexRouter(rules)
    opts = [RouteOption(id=i, description=i) for i in ("refund", "policy")]
    assert router.score("quero a grana de volta", opts)["refund"] == 1.0
    assert router.score("politica do O0001", opts)["policy"] == pytest.approx(0.4)


def test_regex_rules_validation():
    with pytest.raises(ValidationError, match="undefined"):
        RegexRules.model_validate({"rules": {"a": [{"pattern": "{{NOPE}}"}]}})
    with pytest.raises(ValidationError, match="weight 0"):
        RegexRules.model_validate({"rules": {"a": [{"pattern": "x", "weight": 0}]}})


async def test_regex_history_is_weighted():
    rules = RegexRules.model_validate({"rules": {"a": [{"pattern": "boleto"}]}})
    inp = RoutingInput(
        message="sim", level="skill", history=[Message(role="user", content="boleto")]
    )
    opts = [RouteOption(id="a", description="a")]
    assert (await RegexRouter(rules).route(inp, opts)).choice is None
    d = await RegexRouter(rules, history_turns=1, history_weight=0.3).route(inp, opts)
    assert d.choice == "a" and d.candidates == [("a", 0.3)]
