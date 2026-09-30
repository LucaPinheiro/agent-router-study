"""Spend ledger + hard budget caps: persistence, abort before exceeding, run refusal."""

from __future__ import annotations

import json

import pytest

from routing_study.budget import (
    BudgetExceededError,
    CallMeter,
    Price,
    SpendLedger,
    ledger_for,
    load_prices,
)
from routing_study.eval.runner import Runner
from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput
from routing_study.routers.pipeline import RoutingPipeline
from routing_study.settings import PipelineStep, StageConfig, load_settings

E9 = "config/experiments/e9_regex_jev_llm.yaml"


def test_price_table_file_has_both_bedrock_models():
    prices = load_prices("config/prices.yaml")
    sonnet = prices[("bedrock", "global.anthropic.claude-sonnet-5")]
    haiku = prices[("bedrock", "global.anthropic.claude-haiku-4-5-20251001-v1:0")]
    assert (sonnet.input, sonnet.output, sonnet.cache_read, sonnet.cache_write) == (2, 10, 0.2, 2.5)
    assert (haiku.input, haiku.output, haiku.cache_read, haiku.cache_write) == (1, 5, 0.1, 1.25)


def test_price_cost_splits_prompt_tokens():
    p = Price(input=1.0, output=5.0, cache_read=0.1, cache_write=1.25)
    cost = p.cost(prompt_tokens=1_000_000, completion_tokens=0, cache_read=500_000)
    assert cost == pytest.approx(0.5 * 1.0 + 0.5 * 0.1)


def test_ledger_persists_and_reloads_totals(tmp_path):
    path = tmp_path / "ledger.jsonl"
    led = SpendLedger(path, {"aws": 1.0, "openrouter": 1.0})
    with CallMeter(led, "bedrock", "m", 0.01) as meter:
        meter.done({"cost_usd": 0.25, "prompt_tokens": 10, "completion_tokens": 2})
    with CallMeter(led, "ollama", "local", 0.0) as meter:
        meter.done({"cost_usd": 0.0, "prompt_tokens": 5})
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    assert [r["provider"] for r in rows] == ["bedrock", "ollama"]
    assert all("wall_ms" in r and "ts" in r for r in rows)
    again = SpendLedger(path, {"aws": 1.0})
    assert again.spent == {"aws": 0.25}


def test_reservation_blocks_a_call_that_would_exceed_the_cap(tmp_path):
    led = SpendLedger(tmp_path / "l.jsonl", {"aws": 0.30, "openrouter": 1.0})
    with CallMeter(led, "bedrock", "m", 0.0) as meter:
        meter.done({"cost_usd": 0.25})
    with pytest.raises(BudgetExceededError, match="aws budget"):
        with CallMeter(led, "bedrock", "m", 0.10):
            raise AssertionError("the call must not run")
    with CallMeter(led, "ollama", "local", 99.0) as meter:  # local: never capped
        meter.done({"cost_usd": 0.0})
    # in-flight reservations count: two concurrent calls cannot both squeeze under the cap
    first = led.reserve("bedrock", 0.04)
    with pytest.raises(BudgetExceededError):
        led.reserve("bedrock", 0.04)
    led.settle("bedrock", first, None)  # failed call: reservation released, nothing recorded
    led.reserve("bedrock", 0.04)
    assert len(led.rows()) == 2


async def test_bedrock_call_is_refused_before_it_is_sent(tmp_path, monkeypatch):
    from test_providers import FakeConverse, bedrock, tool_reply

    from routing_study.settings import Settings

    monkeypatch.setenv("BUDGET__AWS_USD_CAP", "0.00001")
    s = Settings(_env_file=None)
    client = FakeConverse(tool_reply({"choice": "a", "confidence": 1.0}))
    chat = bedrock(s, client)
    with pytest.raises(BudgetExceededError):
        await chat.ainvoke("x" * 1000)
    assert client.requests == []


async def test_pipeline_lets_the_budget_abort_through():
    class Broke:
        name = "llm"

        async def route(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
            raise BudgetExceededError("cap")

    stage = StageConfig(pipeline=[PipelineStep(strategy="llm")])
    pipe = RoutingPipeline(stage, {"llm": Broke()}, mode="single")
    with pytest.raises(BudgetExceededError):
        await pipe.run(
            RoutingInput(message="m", level="skill"), [RouteOption(id="a", description="")]
        )


async def test_run_refuses_when_projection_exceeds_the_cap(monkeypatch):
    from routing_study.eval import estimate

    async def prices(_settings):
        return {
            "global.anthropic.claude-sonnet-5": (2e-6, 1e-5),
            "typesafe/jev-router": (1e-6, 1e-6),
            "qwen3-embedding:8b-q8_0": (0.0, 0.0),
            "qwen3:8b-q8_0": (0.0, 0.0),
        }

    monkeypatch.setattr(estimate, "list_prices", prices)
    s = load_settings(E9, _env_file=None)
    runner = Runner(s, split="dev", mode="e2e", run_name="t")
    await runner.check_budget(10)  # a few cents: fine
    led = ledger_for(s)  # spend committed to the ledger file (as another process would)
    led.settle("bedrock", 0.0, {"model": "m", "cost_usd": s.budget.aws_usd_cap - 0.01})
    with pytest.raises(BudgetExceededError, match="projected run"):
        await runner.check_budget(10)
    led.settle("bedrock", 0.0, {"model": "m", "cost_usd": -(s.budget.aws_usd_cap - 0.01)})
    s.budget.openrouter_usd_cap = 0.0  # jev projected > 0 on OpenRouter
    with pytest.raises(BudgetExceededError, match="openrouter budget"):
        await runner.check_budget(10)
