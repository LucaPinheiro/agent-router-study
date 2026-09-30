"""Experiment settings loading/overrides and Langfuse span naming (isolated subprocess)."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from routing_study.routers.common import tracing_active
from routing_study.settings import load_settings

EXPERIMENTS = sorted(Path("config/experiments").glob("e*.yaml"))


def test_all_ten_experiments_load():
    assert [p.stem.split("_")[0] for p in EXPERIMENTS] == [f"e{i}" for i in range(10)]
    for path in EXPERIMENTS:
        s = load_settings(path)
        assert s.executor is not None and s.executor.model == "anthropic/claude-sonnet-5"
        assert s.routing.tool.expose_top_k == 2
        if s.routing.mode != "native":
            assert s.routing.skill.pipeline and s.routing.tool.pipeline
            assert s.strategies.embedding.model == "qwen/qwen3-embedding-8b"
            assert s.strategies.jev.model == "typesafe/jev-router"
    assert load_settings(EXPERIMENTS[0]).routing.mode == "native"
    assert load_settings(EXPERIMENTS[6]).strategies.llm.model == "anthropic/claude-haiku-4.5"
    assert load_settings(EXPERIMENTS[5]).strategies.llm.model == "anthropic/claude-sonnet-5"


def test_env_overrides_with_list_index_and_nesting(monkeypatch):
    monkeypatch.setenv("ROUTING__SKILL__PIPELINE__0__MIN_CONFIDENCE", "0.95")
    monkeypatch.setenv("ROUTING__MODE", "shadow")
    monkeypatch.setenv("STRATEGIES__LLM__MODEL", "anthropic/claude-haiku-4.5")
    monkeypatch.setenv("MCP_URL", "http://mcp.test/mcp")
    s = load_settings("config/experiments/e9_regex_jev_llm.yaml")
    assert s.routing.skill.pipeline[0].min_confidence == 0.95
    assert s.routing.skill.pipeline[1].min_confidence == 0.75  # untouched
    assert s.routing.mode == "shadow"
    assert s.strategies.llm.model == "anthropic/claude-haiku-4.5"
    assert s.strategies.jev.model == "typesafe/jev-router"
    assert s.mcp_url == "http://mcp.test/mcp"
    assert s.experiment_id == "e9_regex_jev_llm"


def test_empty_nested_env_override_is_ignored(monkeypatch):
    """B10: `ROUTING__MODE=` (empty, e.g. a blank .env line) must not crash json.loads."""
    monkeypatch.setenv("ROUTING__MODE", "")
    monkeypatch.setenv("STRATEGIES__LLM__MODEL", "")
    s = load_settings("config/experiments/e9_regex_jev_llm.yaml")
    assert s.routing.mode == "cascade"
    assert s.strategies.llm.model == "anthropic/claude-sonnet-5"


@pytest.mark.parametrize(
    "patch",
    [
        {"routing": {"skil": {}}},  # typo of `skill`
        {"strategies": {"llm": {"model": "a/b", "temprature": 0.2}}},
        {"routing": {"skill": {"pipeline": [{"strategy": "regex", "min_confidenc": 0.9}]}}},
    ],
)
def test_config_typos_are_rejected(tmp_path, patch):
    """B11: a misspelled config key must fail loudly, not be silently dropped."""
    from pydantic import ValidationError

    path = tmp_path / "e_typo.yaml"
    path.write_text(json.dumps(patch), encoding="utf-8")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_settings(path, _env_file=None)


def test_defaults_without_experiment(monkeypatch):
    monkeypatch.delenv("MCP_URL", raising=False)
    s = load_settings(None, _env_file=None)
    assert s.mcp_url == "http://localhost:8765/mcp"


def test_missing_experiment_file():
    with pytest.raises(FileNotFoundError):
        load_settings("config/experiments/nope.yaml")


def test_tracing_is_noop_without_langfuse(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    assert tracing_active() is False


SCRIPT = textwrap.dedent(
    """
    import asyncio, json
    from langfuse import Langfuse
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from routing_study.routers.base import RouteOption, RoutingInput
    from routing_study.routers.regex import RegexRouter, RegexRules
    from routing_study.routers.common import tracing_active

    exporter = InMemorySpanExporter()
    lf = Langfuse(public_key="pk-test", secret_key="sk-test", base_url="http://127.0.0.1:9",
                  span_exporter=exporter)
    assert tracing_active()
    rules = RegexRules.model_validate({"rules": {"a": [{"pattern": "x", "weight": 1.0}]}})
    opts = [RouteOption(id="a", description=""), RouteOption(id="b", description="")]
    d = asyncio.run(RegexRouter(rules).route(RoutingInput(message="x", level="tool"), opts))

    from routing_study.routers.base import RouteDecision
    from routing_study.routers.common import BaseRouter

    class Paid(BaseRouter):
        name = "llm"
        paid = True

        async def _decide(self, inp, options):
            return RouteDecision(choice="b", confidence=0.7, strategy="llm", cost_usd=0.0123,
                                 usage={"served_model": "vendor/served", "prompt_tokens": 5,
                                        "completion_tokens": 2})

    asyncio.run(Paid().route(RoutingInput(message="x", level="skill"), opts))
    lf.flush()
    spans = [{"name": s.name, "attrs": dict(s.attributes)} for s in exporter.get_finished_spans()]
    print(json.dumps({"choice": d.choice, "spans": spans}, default=str))
    """
)


def test_route_span_named_and_annotated_when_langfuse_enabled():
    out = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, timeout=60, check=True
    )
    data = json.loads(out.stdout.strip().splitlines()[-1])
    assert data["choice"] == "a"
    names = [s["name"] for s in data["spans"]]
    assert "route.tool.regex" in names, names
    span = next(s for s in data["spans"] if s["name"] == "route.tool.regex")
    blob = json.dumps(span["attrs"])
    assert "choice" in blob and "confidence" in blob and "candidates" in blob
    gen = next(s for s in data["spans"] if s["name"] == "route.skill.llm")
    gblob = json.dumps(gen["attrs"])
    assert "generation" in gblob and "vendor/served" in gblob and "0.0123" in gblob


def test_unit_tests_are_hermetic():
    """B14: no developer `.env` / ambient ROUTING__*, OTEL_*, MAX_RATE_LIMIT_WAIT_S leaks in."""
    import os

    from routing_study.settings import Settings

    s = Settings()
    assert len(s.openrouter_api_key) == 0  # never print the secret on failure
    assert s.max_rate_limit_wait_s == 65.0 and s.redis_url is None
    assert load_settings("config/experiments/e9_regex_jev_llm.yaml").routing.mode == "cascade"
    assert not [k for k in os.environ if k.startswith(("OTEL_", "ROUTING__", "LANGFUSE_"))]
