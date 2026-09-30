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
    return Settings(_env_file=None, openrouter_api_key="k", openrouter_base_url=BASE,
                    http_retries=2)


def test_provider_extra_body():
    assert provider_extra_body(None) == {"usage": {"include": True}}
    body = provider_extra_body(ProviderPrefs(order=["anthropic"], allow_fallbacks=False))
    assert body["provider"] == {"allow_fallbacks": False, "order": ["anthropic"]}


def test_make_chat_model_params(settings):
    m = make_chat_model(settings, "x/y", temperature=0, seed=7,
                        provider=ProviderPrefs(order=["p"], allow_fallbacks=False))
    assert m.model_name == "x/y" and m.temperature == 0 and m.seed == 7
    assert m.max_retries == 0  # tenacity owns retries
    assert m.extra_body["usage"] == {"include": True}
    assert m.extra_body["provider"]["order"] == ["p"]
    dropped = make_chat_model(settings, "x/y", temperature=0, seed=7, supported_parameters=[])
    assert dropped.temperature is None and dropped.seed is None


@respx.mock
async def test_chat_response_exposes_cost_served_model_and_provider(settings):
    respx.post(f"{BASE}/chat/completions").mock(return_value=httpx.Response(200, json={
        "id": "gen-1", "object": "chat.completion", "created": 1,
        "model": "openai/gpt-6-luna", "provider": "OpenAI",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": "hi"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4,
                  "cost": 2.5e-05, "completion_tokens_details": {"reasoning_tokens": 1}},
    }))
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
    route = respx.post(f"{BASE}/embeddings").mock(side_effect=[
        httpx.Response(503, json={"error": "busy"}),
        httpx.Response(200, json={
            "model": "Qwen/Qwen3-Embedding-8B", "provider": "Nebius",
            "data": [{"index": 1, "embedding": [0.0, 1.0]},
                     {"index": 0, "embedding": [1.0, 0.0]}],
            "usage": {"prompt_tokens": 8, "cost": 8e-08},
        }),
    ])
    client = EmbeddingsClient(settings, "qwen/qwen3-embedding-8b",
                              provider=ProviderPrefs(order=["nebius"]))
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
    s = load_settings("config/experiments/e9_regex_jev_llm.yaml", openrouter_api_key="k",
                      openrouter_base_url=BASE)
    chat, emb = configured_models(s)
    assert chat == {"anthropic/claude-sonnet-5", "typesafe/jev-router"}
    assert emb == {"qwen/qwen3-embedding-8b"}
    respx.get(f"{BASE}/models").mock(return_value=httpx.Response(
        200, json=_models_payload(sorted(chat))))
    respx.get(f"{BASE}/embeddings/models").mock(return_value=httpx.Response(
        200, json=_models_payload(sorted(emb))))
    info = await validate_models(s)
    assert info["typesafe/jev-router"] == ["temperature"]

    respx.get(f"{BASE}/models").mock(return_value=httpx.Response(
        200, json=_models_payload(["anthropic/claude-sonnet-5"])))
    with pytest.raises(UnknownModelError, match="typesafe/jev-router"):
        await validate_models(s)
