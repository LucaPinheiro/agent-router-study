"""Provider layer with mocks: Bedrock (fake Converse client), Ollama (respx), unified usage,
structured output, logprob confidence, strategy mapping and the shadow set."""

from __future__ import annotations

import json
import math
from typing import Any

import httpx
import pytest
import respx
from botocore.exceptions import ClientError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from routing_study.budget import Price, ledger_for
from routing_study.llm import (
    BedrockChat,
    EmbeddingsClient,
    bedrock_cache_points,
    bedrock_token_usage,
    chat_model_for,
    extract_call_usage,
    make_ollama_chat,
)
from routing_study.routers.base import RouteOption, RoutingInput
from routing_study.routers.llm import LLMRouter, choice_probability
from routing_study.routers.pipeline import shadow_set
from routing_study.settings import (
    LLMStrategy,
    Settings,
    StrategiesConfig,
    load_settings,
)

SONNET = "global.anthropic.claude-sonnet-5"
HAIKU = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
PRICE = Price(input=2.0, output=10.0, cache_read=0.2, cache_write=2.5, cache_write_1h=4.0)
OLLAMA = "http://localhost:11434/v1"
OPTS = [
    RouteOption(id="pagamentos", description="boletos e reembolsos"),
    RouteOption(id="logistica", description="entrega e rastreio"),
]


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(_env_file=None, cache_dir=str(tmp_path / "cache"), http_retries=2)


# ---------------------------------------------------------------- Bedrock (fake client)


class FakeConverse:
    """Stands in for the boto3 bedrock-runtime client: records requests, replays replies."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return json.loads(json.dumps(reply))  # langchain-aws pops keys: hand out a copy


def converse_reply(content: list[dict[str, Any]], usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": "tool_use" if any("toolUse" in c for c in content) else "end_turn",
        "usage": usage,
        "metrics": {"latencyMs": 5},
    }


def tool_reply(args: dict[str, Any], **usage: int) -> dict[str, Any]:
    use = {"toolUse": {"toolUseId": "t1", "name": "RouteChoice", "input": args}}
    return converse_reply([use], {"inputTokens": 10, "outputTokens": 5, **usage})


def bedrock(
    settings: Settings, client: FakeConverse, model: str = SONNET, **kw: Any
) -> BedrockChat:
    return BedrockChat(
        model=model,
        region_name="sa-east-1",
        client=client,
        bedrock_client=object(),
        max_tokens=64,
        price=PRICE,
        ledger=ledger_for(settings),
        **kw,
    )


def throttled() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse"
    )


def test_bedrock_token_usage_prices_cache_read_and_write():
    msg = AIMessage(
        "",
        usage_metadata={
            "input_tokens": 1000 + 4000 + 500,  # uncached + cache read + cache write
            "output_tokens": 100,
            "total_tokens": 5600,
            "input_token_details": {
                "cache_read": 4000,
                "cache_creation": 0,
                "ephemeral_5m_input_tokens": 500,
            },
        },
    )
    tu = bedrock_token_usage(msg, PRICE)
    expected = (1000 * 2.0 + 100 * 10.0 + 4000 * 0.2 + 500 * 2.5) / 1e6
    assert tu["cost"] == pytest.approx(expected)
    assert tu["prompt_tokens_details"] == {"cached_tokens": 4000, "cache_write_tokens": 500}


def test_cache_control_blocks_become_converse_cache_points():
    sys = SystemMessage(
        [
            {"type": "text", "text": "static", "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "dynamic"},
        ]
    )
    out = bedrock_cache_points([sys, HumanMessage("hi")])
    assert out[0].content == [
        {"type": "text", "text": "static"},
        {"cachePoint": {"type": "default"}},
        {"type": "text", "text": "dynamic"},
    ]
    assert out[1].content == "hi"


async def test_bedrock_router_structured_output_cost_and_ledger(settings):
    client = FakeConverse(
        tool_reply(
            {"choice": "pagamentos", "confidence": 0.9},
            cacheReadInputTokens=2000,
            cacheWriteInputTokens=0,
        )
    )
    chat = bedrock(settings, client)
    router = LLMRouter(chat, settings, model=SONNET)
    d = await router.route(RoutingInput(message="boleto", level="skill"), OPTS)
    assert (d.choice, d.confidence) == ("pagamentos", 0.9)
    assert d.cost_usd == pytest.approx((10 * 2.0 + 5 * 10.0 + 2000 * 0.2) / 1e6)
    assert d.usage["provider"] == "bedrock" and d.usage["cache_read"] == 2000
    req = client.requests[0]
    assert req["toolConfig"]["toolChoice"] == {"tool": {"name": "RouteChoice"}}  # forced tool
    assert "temperature" not in req.get("inferenceConfig", {})  # null temperature: never sent
    # the routing prompt's static block is cached on Anthropic models
    assert {"cachePoint": {"type": "default"}} in req["system"]
    rows = ledger_for(settings).rows()
    assert rows[-1]["provider"] == "bedrock" and rows[-1]["cost_usd"] == pytest.approx(d.cost_usd)


async def test_bedrock_throttling_is_retried(settings):
    client = FakeConverse(throttled(), tool_reply({"choice": "logistica", "confidence": 0.7}))
    router = LLMRouter(bedrock(settings, client), settings, model=SONNET)
    d = await router.route(RoutingInput(message="rastreio", level="skill"), OPTS)
    assert d.choice == "logistica" and d.usage["attempts"] == 2
    assert len(ledger_for(settings).rows()) == 1  # the throttled attempt cost nothing


async def test_bedrock_temperature_zero_is_sent_and_tool_choice_none(settings):
    reply = converse_reply([{"text": "ok"}], {"inputTokens": 3, "outputTokens": 1})
    client = FakeConverse(reply)
    chat = bedrock(settings, client, model=HAIKU, temperature=0.0)  # Haiku accepts temperature
    tool = {
        "type": "function",
        "function": {"name": "get_order", "description": "d", "parameters": {"type": "object"}},
    }
    bound = chat.bind_tools([tool], tool_choice="none", parallel_tool_calls=False)
    ai = AIMessage("", tool_calls=[{"name": "get_order", "args": {}, "id": "t1"}])
    out = await bound.ainvoke([HumanMessage("x"), ai, ToolMessage("done", tool_call_id="t1")])
    req = client.requests[0]
    assert req["inferenceConfig"]["temperature"] == 0.0
    assert req["additionalModelRequestFields"] == {"tool_choice": {"type": "none"}}
    assert extract_call_usage(out)["cost_usd"] == pytest.approx((3 * 2.0 + 1 * 10.0) / 1e6)


def test_factory_dispatches_by_provider(settings):
    bed = chat_model_for(settings, LLMStrategy(provider="bedrock", model=SONNET, temperature=None))
    assert isinstance(bed, BedrockChat) and bed.temperature is None
    assert bed.region_name == "sa-east-1" and bed.max_retries == 0
    loc = chat_model_for(settings, LLMStrategy(provider="ollama", model="qwen3:8b-q8_0"))
    assert loc.openai_api_base == OLLAMA and loc.reasoning_effort == "none"  # thinking off
    with pytest.raises(ValueError, match="no bedrock price"):
        chat_model_for(settings, LLMStrategy(provider="bedrock", model="x.unpriced"))


# ---------------------------------------------------------------- Ollama (respx)


def ollama_completion(content: str, logprobs: list[tuple[str, float]] | None = None) -> dict:
    choice: dict[str, Any] = {
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": content},
    }
    if logprobs is not None:
        choice["logprobs"] = {
            "content": [
                {"token": t, "logprob": lp, "bytes": None, "top_logprobs": []} for t, lp in logprobs
            ]
        }
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "qwen3:8b-q8_0",
        "system_fingerprint": "fp_ollama",
        "choices": [choice],
        "usage": {"prompt_tokens": 200, "completion_tokens": 20, "total_tokens": 220},
    }


@respx.mock
async def test_ollama_router_strict_schema_thinking_off(settings):
    route = respx.post(f"{OLLAMA}/chat/completions").mock(
        return_value=httpx.Response(
            200, json=ollama_completion('{"choice": "logistica", "confidence": 0.8}')
        )
    )
    chat = make_ollama_chat(
        settings, "qwen3:8b-q8_0", temperature=0, http_async_client=httpx.AsyncClient()
    )
    router = LLMRouter(chat, settings, model="qwen3:8b-q8_0", name="llm_local")
    d = await router.route(RoutingInput(message="cade meu pedido", level="skill"), OPTS)
    body = json.loads(route.calls[0].request.content)
    assert body["reasoning_effort"] == "none"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"]["properties"]["choice"]["enum"] == [
        "pagamentos",
        "logistica",
    ]
    assert (d.strategy, d.choice, d.confidence, d.cost_usd) == ("llm_local", "logistica", 0.8, 0.0)
    assert (d.usage["provider"], d.usage["prompt_tokens"]) == ("ollama", 200)
    row = ledger_for(settings).rows()[-1]
    assert (row["provider"], row["cost_usd"], row["prompt_tokens"]) == ("ollama", 0.0, 200)


@respx.mock
async def test_ollama_logprob_confidence(settings):
    tokens = [('{"', 0.0), ("choice", 0.0), ('":', 0.0), (' "', 0.0), ("log", -0.1),
              ("istica", -0.2), ('",', 0.0), (' "', 0.0), ("confidence", 0.0), ('":', 0.0),
              (" 0.99", 0.0), ("}", 0.0)]  # fmt: skip
    route = respx.post(f"{OLLAMA}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json=ollama_completion('{"choice": "logistica", "confidence": 0.99}', tokens),
        )
    )
    chat = make_ollama_chat(
        settings, "qwen3:8b-q8_0", logprobs=True, http_async_client=httpx.AsyncClient()
    )
    router = LLMRouter(chat, settings, model="qwen3:8b-q8_0", confidence="logprob")
    d = await router.route(RoutingInput(message="cade meu pedido", level="skill"), OPTS)
    body = json.loads(route.calls[0].request.content)
    assert body["logprobs"] is True
    assert body["response_format"] == {"type": "json_object"}  # natural tokens, not a grammar
    assert d.confidence == pytest.approx(math.exp(-0.3))
    assert d.usage["self_reported_confidence"] == 0.99


def test_choice_probability_needs_logprobs():
    assert choice_probability(AIMessage("x"), "a") is None
    assert choice_probability(None, "a") is None


def test_logprob_confidence_needs_a_logprob_provider():
    with pytest.raises(ValueError, match="logprob"):
        LLMStrategy(provider="bedrock", model=SONNET, confidence="logprob")


@respx.mock
async def test_ollama_embeddings_prefix_queries_only(settings):
    seen: list[list[str]] = []

    def reply(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["input"])
        assert "Authorization" not in request.headers  # local: no key sent anywhere
        data = [{"index": i, "embedding": [1.0, float(i)]} for i in range(len(body["input"]))]
        return httpx.Response(
            200, json={"model": body["model"], "data": data, "usage": {"prompt_tokens": 7}}
        )

    respx.post(f"{OLLAMA}/embeddings").mock(side_effect=reply)
    client = EmbeddingsClient(
        settings,
        "qwen3-embedding:8b-q8_0",
        backend="ollama",
        query_instruction="Instruct: route\nQuery:",
        http=httpx.AsyncClient(),
    )
    docs = await client.embed(["documento"])
    q = await client.embed_query("mensagem")
    assert seen == [["documento"], ["Instruct: route\nQuery:mensagem"]]
    assert (q.provider, q.cost_usd, docs.vectors.shape) == ("ollama", 0.0, (1, 2))
    rows = ledger_for(settings).rows()
    assert [r["provider"] for r in rows] == ["ollama", "ollama"]


# ---------------------------------------------------------------- config / mapping


def test_legacy_provider_prefs_still_load():
    cfg = LLMStrategy.model_validate({"model": "a/b", "provider": {"order": ["x"]}})
    assert cfg.provider == "openrouter" and cfg.openrouter.order == ["x"]
    with pytest.raises(ValueError, match="openrouter"):
        LLMStrategy(provider="ollama", model="m", openrouter={"order": ["x"]})


def test_extra_llm_strategies_are_a_name_to_model_mapping():
    cfg = StrategiesConfig.model_validate(
        {
            "llm": {"model": "a/b"},
            "llm_local": {"provider": "ollama", "model": "m1"},
            "llm_local_large": {"provider": "ollama", "model": "m2"},
        }
    )
    assert isinstance(cfg.llm_local_large, LLMStrategy)
    assert list(cfg.llm_strategies()) == ["llm", "llm_local", "llm_local_large"]
    assert cfg.configured() == ["llm", "llm_local", "llm_local_large"]
    with pytest.raises(ValueError, match="unknown strategy block"):
        StrategiesConfig.model_validate({"lmm": {"model": "a/b"}})
    with pytest.raises(ValueError):
        StrategiesConfig.model_validate({"llm_x": {"model": "a/b", "tempeature": 0}})


def test_shadow_set_keeps_local_llms_out_when_models_do_not_fit():
    s = load_settings("config/experiments/e9_regex_jev_llm.yaml", _env_file=None)
    # embedder + 8B + 32B = 3 local models > 1 loaded at a time
    assert shadow_set(s) == ["regex", "bm25", "embedding", "llm", "jev", "hybrid"]
    s.ollama_max_loaded_models = 3
    assert "llm_local" in shadow_set(s) and "llm_local_large" in shadow_set(s)
    s.routing.shadow_strategies = ["regex", "llm_local"]
    assert shadow_set(s) == ["regex", "llm_local"]
    e6b = load_settings("config/experiments/e6b_llm_qwen3_local.yaml", _env_file=None)
    # its own pipeline step stays; the other local LLM does not join the pass
    assert "llm_local" in shadow_set(e6b) and "llm_local_large" not in shadow_set(e6b)


@respx.mock
async def test_openrouter_cost_reaches_the_ledger(settings):
    from routing_study.llm import make_chat_model

    BASE_URL = "https://openrouter.test/api/v1"
    body = ollama_completion("oi") | {"model": "openai/x", "provider": "Azure"}
    body["usage"] = {"prompt_tokens": 100, "completion_tokens": 10, "cost": 0.0003}
    respx.post(f"{BASE_URL}/chat/completions").mock(return_value=httpx.Response(200, json=body))
    s = settings.model_copy(update={"openrouter_base_url": BASE_URL})
    chat = make_chat_model(s, "typesafe/jev-router", http_async_client=httpx.AsyncClient())
    msg = await chat.ainvoke("x")
    assert extract_call_usage(msg)["cost_usd"] == pytest.approx(0.0003)
    row = ledger_for(s).rows()[-1]
    assert (row["provider"], row["cost_usd"], row["prompt_tokens"]) == ("openrouter", 0.0003, 100)


async def test_ollama_calls_queue_client_side_for_the_server_slots(settings):
    import asyncio

    from routing_study.llm import RetryStats, call_with_retry

    running = 0
    peak = 0

    async def call() -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1

    stats = [RetryStats(), RetryStats()]
    await asyncio.gather(
        *(
            call_with_retry(call, model=f"m{i}", settings=settings, stats=st, provider="ollama")
            for i, st in enumerate(stats)
        )
    )
    assert peak == 1  # one slot (ollama_num_parallel=1), even across local models
    assert max(st.queue_ms for st in stats) >= 40  # the wait is queue time, not latency
    assert all(st.call_ms < 100 for st in stats)
