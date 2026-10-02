"""llm.py: OpenRouter chat factory, usage/cost extraction, embeddings, retries, slug checks."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from langchain_core.messages import AIMessage

from routing_study.llm import (
    EmbeddingsClient,
    UnknownModelError,
    call_with_retry,
    configured_models,
    extract_call_usage,
    make_chat_model,
    provider_extra_body,
    validate_models,
)
from routing_study.settings import ProviderPrefs, Settings, load_settings

BASE = "https://openrouter.test/api/v1"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None, openrouter_api_key="k", openrouter_base_url=BASE, http_retries=2
    )


def test_provider_extra_body():
    assert provider_extra_body(None) == {"usage": {"include": True}}
    body = provider_extra_body(ProviderPrefs(order=["anthropic"], allow_fallbacks=False))
    assert body["provider"] == {"allow_fallbacks": False, "order": ["anthropic"]}


def test_make_chat_model_params(settings):
    m = make_chat_model(
        settings,
        "x/y",
        temperature=0,
        seed=7,
        provider=ProviderPrefs(order=["p"], allow_fallbacks=False),
    )
    assert m.model_name == "x/y" and m.temperature == 0 and m.seed == 7
    assert m.max_retries == 0  # tenacity owns retries
    assert m.extra_body["usage"] == {"include": True}
    assert m.extra_body["provider"]["order"] == ["p"]
    dropped = make_chat_model(settings, "x/y", temperature=0, seed=7, supported_parameters=[])
    assert dropped.temperature is None and dropped.seed is None


@respx.mock
async def test_chat_response_exposes_cost_served_model_and_provider(settings):
    respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "gen-1",
                "object": "chat.completion",
                "created": 1,
                "model": "openai/gpt-6-luna",
                "provider": "OpenAI",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "hi"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 1,
                    "total_tokens": 4,
                    "cost": 2.5e-05,
                    "completion_tokens_details": {"reasoning_tokens": 1},
                },
            },
        )
    )
    chat = make_chat_model(settings, "typesafe/jev-router", http_async_client=httpx.AsyncClient())
    msg = await chat.ainvoke("hi")
    u = extract_call_usage(msg)
    assert u["cost_usd"] == pytest.approx(2.5e-05) and u["cost_reported"]
    assert u["served_model"] == "openai/gpt-6-luna" and u["provider"] == "OpenAI"
    assert u["prompt_tokens"] == 3 and u["reasoning_tokens"] == 1
    assert u["generation_id"] == "gen-1"


def test_extract_usage_without_cost():
    u = extract_call_usage(AIMessage("x", response_metadata={"token_usage": {}}))
    assert u["cost_usd"] == 0.0 and u["cost_reported"] is False
    assert extract_call_usage(None) == {"cost_usd": 0.0}


@respx.mock
async def test_embeddings_client_vectors_cost_provider_and_retry(settings):
    route = respx.post(f"{BASE}/embeddings").mock(
        side_effect=[
            httpx.Response(503, json={"error": "busy"}),
            httpx.Response(
                200,
                json={
                    "model": "Qwen/Qwen3-Embedding-8B",
                    "provider": "Nebius",
                    "data": [
                        {"index": 1, "embedding": [0.0, 1.0]},
                        {"index": 0, "embedding": [1.0, 0.0]},
                    ],
                    "usage": {"prompt_tokens": 8, "cost": 8e-08},
                },
            ),
        ]
    )
    client = EmbeddingsClient(
        settings, "qwen/qwen3-embedding-8b", provider=ProviderPrefs(order=["nebius"])
    )
    res = await client.embed(["a", "b"])
    await client.aclose()
    assert res.vectors.tolist() == [[1.0, 0.0], [0.0, 1.0]]  # re-ordered by index
    assert res.cost_usd == pytest.approx(8e-08) and res.provider == "Nebius"
    assert res.served_model == "Qwen/Qwen3-Embedding-8B" and res.attempts == 2
    body = json.loads(route.calls.last.request.content)
    assert body["usage"] == {"include": True} and body["provider"]["order"] == ["nebius"]
    assert route.calls.last.request.headers["Authorization"] == "Bearer k"


async def test_call_with_retry_does_not_retry_client_errors(settings):
    calls = 0

    async def bad() -> None:
        nonlocal calls
        calls += 1
        req = httpx.Request("GET", "http://x")
        raise httpx.HTTPStatusError("400", request=req, response=httpx.Response(400, request=req))

    with pytest.raises(httpx.HTTPStatusError):
        await call_with_retry(bad, model="a/b", settings=settings)
    assert calls == 1


async def test_call_with_retry_gives_up_after_budget(settings):
    calls = 0

    async def flaky() -> None:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        await call_with_retry(flaky, model="a/b", settings=settings)
    assert calls == settings.http_retries + 1


def _models_payload(ids: list[str]) -> dict:
    return {"data": [{"id": i, "supported_parameters": ["temperature"]} for i in ids]}


@respx.mock
async def test_validate_models_ok_and_missing():
    s = load_settings(
        "config/experiments/e9_regex_jev_llm.yaml", openrouter_api_key="k", openrouter_base_url=BASE
    )
    chat, emb = configured_models(s)  # OpenRouter slugs only (Bedrock / Ollama elsewhere)
    assert chat == {"typesafe/jev-router"}
    assert emb == set()
    respx.get(f"{BASE}/models").mock(
        return_value=httpx.Response(200, json=_models_payload(sorted(chat)))
    )
    tags = respx.get("http://localhost:11434/api/tags")
    pulled = httpx.Response(
        200,
        json={"models": [{"name": n} for n in ("qwen3:8b-q8_0", "qwen3-embedding:8b-q8_0")]},
    )
    tags.mock(return_value=pulled)
    info = await validate_models(s)
    assert info["typesafe/jev-router"] == ["temperature"]

    tags.mock(return_value=httpx.Response(200, json={"models": [{"name": "qwen3:8b-q8_0"}]}))
    with pytest.raises(UnknownModelError, match="qwen3-embedding:8b-q8_0"):
        await validate_models(s)

    tags.mock(return_value=pulled)
    respx.get(f"{BASE}/models").mock(
        return_value=httpx.Response(200, json=_models_payload(["x/other"]))
    )
    with pytest.raises(UnknownModelError, match="typesafe/jev-router"):
        await validate_models(s)


# ---------------------------------------------------------------- B8: embeddings errors

_EMB_OK = {
    "model": "q/e",
    "data": [{"index": 0, "embedding": [1.0, 0.0]}],
    "usage": {"prompt_tokens": 1, "cost": 1e-8},
}


def test_rate_limit_reset_read_from_httpx_429():
    import time

    from routing_study.llm import _rate_limit_reset_s

    req = httpx.Request("POST", f"{BASE}/embeddings")
    reset = str(int(time.time() * 1000 + 2000))
    by_header = httpx.HTTPStatusError(
        "429",
        request=req,
        response=httpx.Response(429, request=req, headers={"x-ratelimit-reset": reset}),
    )
    by_body = httpx.HTTPStatusError(
        "429",
        request=req,
        response=httpx.Response(
            429,
            request=req,
            json={"error": {"code": 429, "metadata": {"headers": {"X-RateLimit-Reset": reset}}}},
        ),
    )
    for exc in (by_header, by_body):
        wait = _rate_limit_reset_s(exc)
        assert wait is not None and 1.0 < wait <= 2.0


@respx.mock
async def test_embeddings_retry_200_with_transient_error_body(settings):
    route = respx.post(f"{BASE}/embeddings").mock(
        side_effect=[
            httpx.Response(200, json={"error": {"code": 502, "message": "upstream down"}}),
            httpx.Response(200, json=_EMB_OK),
        ]
    )
    client = EmbeddingsClient(settings, "q/e")
    res = await client.embed(["a"])
    await client.aclose()
    assert res.attempts == 2 and route.call_count == 2


@respx.mock
async def test_embeddings_200_with_client_error_body_not_retried(settings):
    route = respx.post(f"{BASE}/embeddings").mock(
        return_value=httpx.Response(200, json={"error": {"code": 400, "message": "bad input"}})
    )
    client = EmbeddingsClient(settings, "q/e")
    with pytest.raises(RuntimeError, match="bad input"):
        await client.embed(["a"])
    await client.aclose()
    assert route.call_count == 1


def test_a16_chat_model_survives_a_closed_event_loop():
    """A16: langchain_openai caches ONE default httpx client per process; its keep-alive
    connections belong to the loop that opened them, so a chat call after an earlier
    `asyncio.run(...)` failed with "Event loop is closed". Two loops, one local keep-alive
    server, the same factory settings: both calls must succeed."""
    import asyncio
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    body = json.dumps(
        {
            "id": "c1",
            "object": "chat.completion",
            "created": 0,
            "model": "x/y",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    ).encode()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"  # keep-alive: the pooled connection is reused

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        s = Settings(
            _env_file=None,
            openrouter_api_key="k",
            openrouter_base_url=f"http://127.0.0.1:{server.server_port}/v1",
        )
        for _ in range(2):  # a fresh model each time, like the runner and the router tests
            chat = make_chat_model(s, "x/y")
            assert asyncio.run(chat.ainvoke("hi")).content == "ok"
    finally:
        server.shutdown()
        server.server_close()


def test_reasoning_is_explicit_in_router_and_executor_requests() -> None:
    """Sonnet 5 reasons by default under structured output; the study pins it off unless the
    config says otherwise, so cost/latency/budget are controlled variables."""
    from routing_study.llm import make_chat_model
    from routing_study.settings import ExecutorConfig, LLMStrategy, ReasoningPrefs, Settings

    s = Settings(_env_file=None)
    router = LLMStrategy(model="anthropic/claude-sonnet-5")
    chat = make_chat_model(
        s, router.model, reasoning=router.reasoning, max_tokens=router.max_tokens
    )
    assert chat.extra_body["reasoning"] == {"enabled": False}
    assert chat.max_tokens == 512

    ex = ExecutorConfig(  # thinking on Anthropic requires temperature 1 or unset (finding 8)
        model="anthropic/claude-sonnet-5",
        temperature=None,
        reasoning={"enabled": True, "effort": "low"},
    )
    chat = make_chat_model(s, ex.model, reasoning=ex.reasoning, max_tokens=ex.max_tokens)
    assert chat.extra_body["reasoning"] == {"enabled": True, "effort": "low"}
    assert ReasoningPrefs().model_dump(exclude_none=True) == {"enabled": False}


def test_jev_router_caps_output_tokens() -> None:
    """Without max_tokens OpenRouter reserves 65536 output tokens per Jev call against credits."""
    from routing_study.routers.pipeline import build_routers
    from routing_study.settings import load_settings

    s = load_settings("config/experiments/e4_jev.yaml")
    jev = build_routers(s, {"jev"}, supported_parameters={})["jev"]
    assert jev.chat.max_tokens == 512


@respx.mock
async def test_billed_reply_that_the_client_rejects_still_reaches_the_ledger(settings):
    """A reply cut by max_tokens under a json_schema format makes the openai client raise
    LengthFinishReasonError AFTER the provider billed it: the spend must be settled anyway,
    and the usage rides on the exception (`call_usage`) for the router's partial usage."""
    import openai

    from routing_study.budget import ledger_for
    from routing_study.llm import structured_runnable

    respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "gen-cut",
                "object": "chat.completion",
                "created": 1,
                "model": "anthropic/claude-sonnet-5",
                "provider": "Anthropic",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "length",
                        "message": {"role": "assistant", "content": '{"choice": "a'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 900,
                    "completion_tokens": 64,
                    "total_tokens": 964,
                    "cost": 0.0042,
                    "prompt_tokens_details": {"cached_tokens": 800, "cache_write_tokens": 0},
                },
            },
        )
    )
    chat = make_chat_model(
        settings, "anthropic/claude-sonnet-5", max_tokens=64, http_async_client=httpx.AsyncClient()
    )
    schema = {
        "title": "Pick",
        "type": "object",
        "properties": {"choice": {"type": "string", "enum": ["a", "b"]}},
        "required": ["choice"],
        "additionalProperties": False,
    }
    before = len(ledger_for(settings).rows())
    with pytest.raises(openai.LengthFinishReasonError) as info:
        await structured_runnable(chat, schema).ainvoke("x")
    rows = ledger_for(settings).rows()
    assert len(rows) == before + 1
    assert rows[-1]["cost_usd"] == pytest.approx(0.0042) and rows[-1]["cache_read"] == 800
    usage = info.value.call_usage  # type: ignore[attr-defined]
    assert usage["cost_usd"] == pytest.approx(0.0042) and usage["completion_tokens"] == 64
    assert usage["served_model"] == "anthropic/claude-sonnet-5"


@pytest.mark.parametrize(
    ("tool_choice", "native"),
    [
        (None, {"type": "auto", "disable_parallel_tool_use": True}),
        ("get_order", {"type": "tool", "name": "get_order", "disable_parallel_tool_use": True}),
    ],
)
async def test_bedrock_executor_disables_parallel_tool_calls(settings, tool_choice, native):
    """F9: Converse has no parallel-tool switch (ToolConfiguration = tools + toolChoice), so
    `parallel_tool_calls=False` goes as Anthropic's native tool_choice (additional fields)."""
    from langchain_core.messages import HumanMessage
    from test_providers import FakeConverse, bedrock, converse_reply

    client = FakeConverse(converse_reply([{"text": "ok"}], {"inputTokens": 3, "outputTokens": 1}))
    tool = {
        "type": "function",
        "function": {"name": "get_order", "description": "d", "parameters": {"type": "object"}},
    }
    chat = bedrock(settings, client)
    bound = chat.bind_tools([tool], tool_choice=tool_choice, parallel_tool_calls=False)
    await bound.ainvoke([HumanMessage("x")])
    req = client.requests[0]
    assert req["additionalModelRequestFields"] == {"tool_choice": native}
    assert "toolChoice" not in req["toolConfig"]  # one source of truth for the choice
    assert chat.additional_model_request_fields is None  # the shared client is not mutated


def test_ollama_untagged_model_matches_latest_tag() -> None:
    """`bge-m3` in a config is `bge-m3:latest` on the server (prereg deviation D-001)."""
    from routing_study.llm import _ollama_tag

    assert _ollama_tag("bge-m3") == "bge-m3:latest"
    assert _ollama_tag("qwen3:8b-q8_0") == "qwen3:8b-q8_0"
    assert _ollama_tag("bge-m3") == _ollama_tag("bge-m3:latest")


def test_bedrock_quirks_for_managed_small_models() -> None:
    from routing_study.llm import bedrock_quirks

    assert bedrock_quirks("mistral.ministral-3-8b-instruct")["tool_choice"] == (
        "auto",
        "any",
        "tool",
    )
    q = bedrock_quirks("nvidia.nemotron-nano-9b-v2")
    assert q["no_think"] == "/no_think" and "tool" in q["tool_choice"]
    assert bedrock_quirks("global.anthropic.claude-sonnet-5") == {}


def test_with_system_prefix_prepends_or_inserts() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage

    from routing_study.llm import with_system_prefix

    out = with_system_prefix([SystemMessage("rules"), HumanMessage("hi")], "/no_think")
    assert out[0].content == "/no_think\nrules" and out[1].content == "hi"
    out = with_system_prefix([HumanMessage("hi")], "/no_think")
    assert isinstance(out[0], SystemMessage) and out[0].content == "/no_think"


def test_bedrock_embeddings_cohere_batch_and_input_type(tmp_path, monkeypatch) -> None:
    import asyncio
    import io
    import json as _json

    from routing_study.llm import EmbeddingsClient
    from routing_study.settings import Settings

    monkeypatch.setenv("BUDGET__LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    calls: list[dict] = []

    class FakeBoto:
        def invoke_model(self, modelId: str, body: str) -> dict:
            b = _json.loads(body)
            calls.append(b)
            vecs = [[1.0, 0.0]] * len(b["texts"])
            return {
                "ResponseMetadata": {"HTTPHeaders": {"x-amzn-bedrock-input-token-count": "5"}},
                "body": io.BytesIO(_json.dumps({"embeddings": {"float": vecs}}).encode()),
            }

    c = EmbeddingsClient(Settings(), "global.cohere.embed-v4:0", backend="bedrock")
    c._boto = FakeBoto()
    docs = asyncio.run(c.embed(["a", "b", "c"]))
    q = asyncio.run(c.embed_search_query(["q"]))
    assert docs.vectors.shape == (3, 2) and docs.prompt_tokens == 5
    assert [x["input_type"] for x in calls] == ["search_document", "search_query"]
    assert abs(docs.cost_usd - 5 * 0.12 / 1e6) < 1e-12 and q.provider == "bedrock"
