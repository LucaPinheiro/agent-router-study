"""Guardrail for "observability done right" (plan §6.4): one E9 case with shadow on, run twice
(the second repetition hits the router cache), read back from the local Langfuse API.

Needs the docker stack (Langfuse :3300, MCP :8765, app Redis) and OpenRouter credit.
Run: uv run pytest -m integration tests/integration -q
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration

E9 = Path("config/experiments/e9_regex_jev_llm.yaml")
SCORES = {
    "skill_correct",
    "tool_correct",
    "args_valid",
    "e2e_success",
    "abstain_correct",
    "resolved_by",
}


def _truthy(v: Any) -> bool:
    return v is True or str(v).lower() == "true"


def _children(obs: list[dict[str, Any]], parent: dict[str, Any]) -> list[dict[str, Any]]:
    return [o for o in obs if o.get("parentObservationId") == parent["id"]]


def _descendants(obs: list[dict[str, Any]], parent: dict[str, Any]) -> list[dict[str, Any]]:
    out, frontier = [], [parent]
    while frontier:
        kids = [o for p in frontier for o in _children(obs, p)]
        out += kids
        frontier = kids
    return out


def _one(nodes: list[dict[str, Any]], name: str) -> dict[str, Any]:
    found = [o for o in nodes if o["name"] == name]
    assert found, f"missing {name!r} in {[o['name'] for o in nodes]}"
    return found[0]


@pytest.fixture(scope="module")
def run_results(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, Any]]:
    load_dotenv(".env")
    from routing_study.eval.runner import Case, Runner
    from routing_study.settings import load_settings
    from routing_study.tracing.langfuse import init

    init()
    # fresh response cache: earlier runs of this test must not pre-answer either repetition
    settings = load_settings(E9, cache_dir=str(tmp_path_factory.mktemp("cache")))
    settings.routing.mode = "shadow"
    case = Case(
        id="it-trace-payment-status",
        category="direto",
        customer_id="C001",
        turns=[{"role": "user", "content": "Qual o status do pagamento do meu pedido O0001?"}],
        expected={
            "acceptable_skills": ["pagamentos_reembolsos"],
            "acceptable_tools": ["get_payment_status"],
            "args": {"order_id": "O0001"},
        },
    )
    run_name = f"it-trace-{int(time.time())}"
    runner = Runner(
        settings, split="integration", mode="e2e", run_name=run_name, reps=2, concurrency=1
    )
    out = asyncio.run(runner.run([case]))
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    out.unlink()
    assert [r["error"] for r in rows] == [None, None]
    return sorted(rows, key=lambda r: r["rep"])


def test_trace_tree_has_every_node_and_the_mcp_server_span(run_results: list[dict]) -> None:
    from routing_study.tracing.langfuse import LangfuseAPI, format_tree

    rec = run_results[0]
    api = LangfuseAPI()
    obs, scores = api.wait(rec["trace_id"], min_obs=20, scores=SCORES)
    print(format_tree(obs))

    [turn] = [o for o in obs if o["name"] == "turn" and not o.get("parentObservationId")]
    top = _children(obs, turn)
    for name in ("ingest", "route_skill", "route_tool", "agent", "tools"):
        _one(top, name)

    route_skill = _one(top, "route_skill")
    meta = route_skill.get("metadata") or {}
    for key in ("choice", "confidence", "candidates", "resolved_by", "cascade_step", "abstained"):
        assert key in meta, f"route_skill metadata lacks {key}: {sorted(meta)}"
    strategies = {o["name"]: o for o in _children(obs, route_skill)}
    for s in ("regex", "bm25", "embedding", "llm", "jev", "hybrid"):
        assert f"route.skill.{s}" in strategies
    decider = rec["skill"]["resolved_by"]
    for name, o in strategies.items():  # plan §6.2: every non-deciding strategy is shadow
        m = o.get("metadata") or {}
        decisive = name == f"route.skill.{decider}"
        assert _truthy(m.get("decisive")) == decisive and _truthy(m.get("shadow")) != decisive, (
            name,
            m,
        )
    assert strategies["route.skill.llm"]["type"] == "GENERATION"

    route_tool = _one(top, "route_tool")
    assert "exposed_tools" in (route_tool.get("metadata") or {})
    assert any(o["name"].startswith("route.tool.") for o in _children(obs, route_tool))

    gens = [
        g
        for a in top
        if a["name"] == "agent"
        for g in _children(obs, a)
        if g["type"] == "GENERATION"
    ]
    assert gens and all((g.get("totalCost") or 0) > 0 for g in gens), gens

    tool_name = next(c["name"] for c in rec["calls"] if c["name"] != "load_skill")
    tools = [t for t in top if t["name"] == "tools"]
    client_calls = [
        c for t in tools for c in _children(obs, t) if c["name"] == f"mcp.client.call {tool_name}"
    ]
    assert client_calls, "no mcp.client.call span under tools"
    assert any(
        d["name"] == f"mcp.tools/call {tool_name}" for d in _descendants(obs, client_calls[0])
    ), "server span not nested"

    names = {s["name"] for s in scores}
    assert SCORES <= names, names


def test_second_repetition_is_an_independent_router_sample(run_results: list[dict]) -> None:
    """The response-cache key includes the repetition (review B1): rep 2 is a new sample, not
    a copy of rep 1; re-running the same repetition is what hits the cache (unit-tested)."""
    from routing_study.tracing.langfuse import LangfuseAPI

    rep2 = run_results[1]
    assert rep2["skill"]["shadow"]["llm"]["cached"] is False
    obs, _ = LangfuseAPI().wait(rep2["trace_id"], min_obs=20)
    llm = _one(obs, "route.skill.llm")
    assert not _truthy((llm.get("metadata") or {}).get("cached"))
    assert (llm.get("totalCost") or 0) > 0
