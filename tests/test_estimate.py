"""eval/estimate.py: the a-priori cost must be a real upper bound (B13)."""

from __future__ import annotations

import pytest

from routing_study.eval import estimate as est
from routing_study.graph.nodes import max_tool_rounds
from routing_study.settings import load_settings

E9 = "config/experiments/e9_regex_jev_llm.yaml"


def _prices(s, **over):
    p = {
        "anthropic/claude-sonnet-5": (1e-6, 1e-5),
        "typesafe/jev-router": (1e-6, 1e-6),
        "qwen/qwen3-embedding-8b": (1e-8, 0.0),
        "anthropic/claude-haiku-4.5": (1e-7, 1e-6),
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
        + call("anthropic/claude-sonnet-5", est.ROUTER_PROMPT, est.ROUTER_COMPLETION)
    )  # skill: regex, jev, llm; tool: jev, llm
    executor_calls = max_tool_rounds(s) + 1  # every tool round + the wrap-up answer
    executor = executor_calls * call(
        "anthropic/claude-sonnet-5", est.EXECUTOR_PROMPT, est.EXECUTOR_COMPLETION
    )
    assert total == pytest.approx(routing + executor)
