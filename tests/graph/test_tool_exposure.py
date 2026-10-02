"""route_tool exposes exactly min(k, n skill tools) skill tools (+ globals) for every strategy."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from graph_fakes import FakeTools, FixedRouter, StaticCatalog, make_catalog
from langgraph.checkpoint.memory import MemorySaver

from routing_study.graph.builder import build_graph
from routing_study.graph.state import RunContext
from routing_study.llm import make_chat_model
from routing_study.routers.base import Router
from routing_study.routers.bm25 import BM25Router
from routing_study.routers.jev import JevRouter
from routing_study.routers.llm import LLMRouter
from routing_study.routers.pipeline import RoutingPipeline
from routing_study.settings import PipelineStep, Settings, StageConfig

BASE_URL = "https://openrouter.test/api/v1"
CATALOG = make_catalog()
SKILL = "pedidos_logistica"
SKILL_TOOLS = set(CATALOG.tools_for(SKILL))  # cancel_order, get_order_status, track_shipment
GLOBALS = set(CATALOG.global_tools)
CASE = {
    "case_id": "c1",
    "customer_id": "C001",
    "split": "dev",
    "repetition": 1,
    "turns": [{"role": "user", "content": "quero o track do pedido O0001"}],
}
RANKED = {
    "choice": "get_order_status",
    "confidence": 0.8,
    "ranking": [
        {"id": "track_shipment", "confidence": 0.15},
        {"id": "escalate_to_human", "confidence": 0.03},
        {"id": "cancel_order", "confidence": 0.02},
    ],
}


@pytest.fixture(autouse=True)
def _no_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")


@pytest.fixture
def settings(tmp_path: Any) -> Settings:
    return Settings(
        _env_file=None,
        openrouter_api_key="test-key",
        openrouter_base_url=BASE_URL,
        cache_dir=str(tmp_path / "cache"),
        http_retries=0,
    )


def _completion(content: str, model: str) -> dict[str, Any]:
    return {
        "id": "gen-test",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "provider": "P",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20, "cost": 1e-5},
    }


def _router(strategy: str, settings: Settings) -> Router:
    if strategy == "bm25":
        return BM25Router()
    if strategy == "regex":  # a router that ranks only its choice
        return FixedRouter(SKILL, "track_shipment")
    model = "anthropic/claude-haiku-4.5" if strategy == "llm" else "typesafe/jev-router"
    chat = make_chat_model(
        settings,
        model,
        supported_parameters=None if strategy == "llm" else [],
        http_async_client=httpx.AsyncClient(),
    )
    if strategy == "llm":
        return LLMRouter(chat, settings, model=model)
    return JevRouter(chat, settings, model=model)


async def _exposed(strategy: str, k: int, settings: Settings) -> list[str]:
    tool_step = [PipelineStep(strategy=strategy)]
    ctx = RunContext(
        settings=settings,
        catalog=StaticCatalog(CATALOG),
        tools=FakeTools(),
        chat=None,
        skill_pipeline=RoutingPipeline(
            StageConfig(pipeline=[PipelineStep(strategy="regex")]),
            {"regex": FixedRouter(SKILL, None)},
        ),
        tool_pipeline=RoutingPipeline(
            StageConfig(pipeline=tool_step, expose_top_k=k), {strategy: _router(strategy, settings)}
        ),
    )
    graph = build_graph(MemorySaver(), routing_only=True)
    state = await graph.ainvoke(
        {"case": CASE}, context=ctx, config={"configurable": {"thread_id": f"{strategy}-{k}"}}
    )
    assert state["outcome"] != "abstained"
    return state["exposed_tools"]


@respx.mock
@pytest.mark.parametrize("strategy", ["bm25", "llm", "jev", "regex"])
@pytest.mark.parametrize("k", [1, 2, 3, 4])
async def test_every_strategy_exposes_min_k_skill_tools(
    strategy: str, k: int, settings: Settings
) -> None:
    respx.post(f"{BASE_URL}/chat/completions").mock(
        side_effect=lambda req: httpx.Response(
            200, json=_completion(json.dumps(RANKED), json.loads(req.content)["model"])
        )
    )
    exposed = await _exposed(strategy, k, settings)
    assert len(set(exposed) & SKILL_TOOLS) == min(k, len(SKILL_TOOLS))
    assert GLOBALS <= set(exposed)
    assert exposed == CATALOG.ordered(exposed)


@respx.mock
@pytest.mark.parametrize("strategy", ["llm", "jev"])
async def test_llm_routers_rank_alternatives_at_tool_level(
    strategy: str, settings: Settings
) -> None:
    route = respx.post(f"{BASE_URL}/chat/completions").mock(
        side_effect=lambda req: httpx.Response(
            200, json=_completion(json.dumps(RANKED), json.loads(req.content)["model"])
        )
    )
    exposed = await _exposed(strategy, 2, settings)
    # the ranking (not the server-order fallback, which would pick cancel_order) fills top-2
    assert set(exposed) & SKILL_TOOLS == {"get_order_status", "track_shipment"}
    assert "ranking" in route.calls.last.request.content.decode()


async def test_ranking_less_router_is_padded_in_server_order(settings: Settings) -> None:
    exposed = await _exposed("regex", 2, settings)
    assert set(exposed) & SKILL_TOOLS == {"track_shipment", "cancel_order"}
