"""eval/estimate.py: the a-priori cost must be a real upper bound (B13)."""

from __future__ import annotations

import pytest

from routing_study.eval import estimate as est
from routing_study.graph.nodes import max_tool_rounds
from routing_study.settings import load_settings

E9 = "config/experiments/e9_regex_jev_llm.yaml"
SONNET = "global.anthropic.claude-sonnet-5"


def _prices(s, **over):
    p = {
        SONNET: (1e-6, 1e-5),
        "typesafe/jev-router": (1e-6, 1e-6),
        "qwen3-embedding:8b-q8_0": (0.0, 0.0),
        "qwen3:8b-q8_0": (0.0, 0.0),
    }
    p.update(over)
    return p


def test_unknown_slug_is_an_error_not_free():
    s = load_settings(E9, _env_file=None)
    prices = _prices(s)
    del prices["typesafe/jev-router"]
    with pytest.raises(ValueError, match="typesafe/jev-router"):
        est.apriori_cost(s, "e2e", prices)


def test_upper_bound_counts_max_executor_calls_and_jev_retries():
    s = load_settings(E9, _env_file=None)
    prices = _prices(s)
    total, _ = est.apriori_cost(s, "e2e", prices)

    def call(model, prompt, completion):
        pin, pout = prices[model]
        return pin * prompt + pout * completion

    jev_calls = s.strategies.jev.parse_retries + 1
    routing = 2 * (
        jev_calls * call("typesafe/jev-router", est.ROUTER_PROMPT, est.ROUTER_COMPLETION)
        + call(SONNET, est.ROUTER_PROMPT, est.ROUTER_COMPLETION)
    )  # skill: regex, jev, llm; tool: jev, llm
    executor_calls = max_tool_rounds(s) + 1  # every tool round + the wrap-up answer
    executor = executor_calls * call(SONNET, est.EXECUTOR_PROMPT, est.EXECUTOR_COMPLETION)
    assert total == pytest.approx(routing + executor)
    by, _ = est.apriori_costs(s, "e2e", prices)  # per billing provider, for the budget guard
    assert by["openrouter"] == pytest.approx(
        2 * jev_calls * call("typesafe/jev-router", est.ROUTER_PROMPT, est.ROUTER_COMPLETION)
    )
    assert by["bedrock"] == pytest.approx(total - by["openrouter"])


async def test_list_prices_uses_the_price_table_for_bedrock_and_zero_for_ollama(monkeypatch):
    s = load_settings(E9, _env_file=None)

    async def _openrouter(_settings):
        return {"typesafe/jev-router": (-1.0, -1.0)}

    monkeypatch.setattr(est, "_prices", _openrouter)
    prices = await est.list_prices(s)
    assert prices[SONNET] == pytest.approx((2e-6, 1e-5))  # config/prices.yaml, USD/1M -> /token
    assert prices["qwen3:8b-q8_0"] == prices["qwen3-embedding:8b-q8_0"] == (0.0, 0.0)
    by, notes = est.apriori_costs(s, "e2e", prices)
    assert by["openrouter"] == 0.0 and "no list price" in notes[0]
