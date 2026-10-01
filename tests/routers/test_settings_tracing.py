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


SONNET = "global.anthropic.claude-sonnet-5"
HAIKU = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


def test_all_experiments_load():
    names = [p.stem.split("_")[0] for p in EXPERIMENTS]
    core = ["e0", "e1", "e2", "e3", "e4", "e5", "e6", "e6b", "e7", "e8", "e9"]
    assert set(core) <= set(names)
    # phase-2 additions: e10 classifier, e11 hybrid, e3 alt-embedder ablations; freeze: e12
    # (exploratory hybrid -> Jev -> LLM cascade)
    assert set(names) - set(core) <= {"e10", "e11", "e12"}
    for path in EXPERIMENTS:
        alt_embedder = path.stem.startswith("e3_embedding_")
        s = load_settings(path)
        ex = s.executor
        assert ex is not None and (ex.provider, ex.model, ex.temperature) == (
            "bedrock",
            SONNET,
            None,
        )
        assert s.routing.tool.expose_top_k == 2
        if s.routing.mode != "native":
            st = s.strategies
            assert s.routing.skill.pipeline and s.routing.tool.pipeline
            assert st.embedding.provider == "ollama"
            if not alt_embedder:
                assert st.embedding.model == "qwen3-embedding:8b-q8_0"
                assert st.embedding.query_instruction.startswith("Instruct: ")
            assert (st.jev.provider, st.jev.model) == ("openrouter", "typesafe/jev-router")
            assert (st.llm_local.provider, st.llm_local.model) == ("ollama", "qwen3:8b-q8_0")
            assert st.llm_local.reasoning.enabled is False  # Qwen3 thinking off
            assert set(st.llm_strategies()) == {"llm", "llm_local"}
    by = {p.stem.split("_")[0]: load_settings(p) for p in EXPERIMENTS}
    assert by["e0"].routing.mode == "native"
    assert (by["e6"].strategies.llm.model, by["e6"].strategies.llm.temperature) == (HAIKU, 0)
    assert (by["e5"].strategies.llm.model, by["e5"].strategies.llm.temperature) == (SONNET, None)
    assert [st.strategy for st in by["e6b"].routing.skill.pipeline] == ["llm_local"]


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
    assert s.strategies.llm.model == SONNET


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
