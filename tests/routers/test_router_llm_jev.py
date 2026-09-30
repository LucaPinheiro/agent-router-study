"""LLM + Jev routers against a mocked OpenRouter (respx), incl. response cache."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from router_helpers import BASE_URL, chat_completion, skill_input

from routing_study.llm import make_chat_model
from routing_study.routers.common import ResponseCache
from routing_study.routers.jev import JevRouter, parse_choice
from routing_study.routers.llm import LLMRouter

CHAT_URL = f"{BASE_URL}/chat/completions"
IDS = ["pedidos_logistica", "pagamentos_reembolsos", "trocas_devolucoes", "__global__"]


def _llm(settings, cache=None, supported=None):
    model = "anthropic/claude-haiku-4.5"
    chat = make_chat_model(settings, model, temperature=0, max_tokens=256,
                           supported_parameters=supported, http_async_client=httpx.AsyncClient())
    return LLMRouter(chat, settings, model=model, cache=cache)


def _jev(settings, cache=None, parse_retries=1):
    model = "typesafe/jev-router"
    chat = make_chat_model(settings, model, supported_parameters=[],
                           http_async_client=httpx.AsyncClient())
    return JevRouter(chat, settings, model=model, parse_retries=parse_retries, cache=cache)


# ------------------------------------------------------------------ llm


@respx.mock
async def test_llm_router_structured_enum_cost_and_provider(settings, skill_options):
    route = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=chat_completion(
        '{"choice": "pagamentos_reembolsos", "confidence": 0.93}')))
    d = await _llm(settings).route(skill_input("2a via do boleto"), skill_options)

    assert d.choice == "pagamentos_reembolsos" and d.confidence == pytest.approx(0.93)
    assert d.cost_usd == pytest.approx(0.0003)
    assert d.usage["served_model"] == "anthropic/claude-haiku-4.5"
    assert d.usage["provider"] == "Anthropic"
    assert d.usage["prompt_tokens"] == 100 and d.latency_ms > 0 and not d.cached

    body = json.loads(route.calls.last.request.content)
    assert body["usage"] == {"include": True}
    assert body["temperature"] == 0
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["choice"]["enum"] == IDS
    assert "2a via do boleto" in body["messages"][-1]["content"]


@respx.mock
async def test_llm_router_drops_unsupported_temperature(settings, skill_options):
    route = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=chat_completion(
        '{"choice": "__global__", "confidence": 0.8}')))
    await _llm(settings, supported=["response_format", "structured_outputs"]).route(
        skill_input("falar com atendente"), skill_options)
    assert "temperature" not in json.loads(route.calls.last.request.content)


@respx.mock
async def test_llm_router_retries_transient_errors(settings, skill_options):
    route = respx.post(CHAT_URL).mock(side_effect=[
        httpx.Response(429, json={"error": {"message": "rate"}}),
        httpx.Response(200, json=chat_completion('{"choice": "__global__", "confidence": 1}')),
    ])
    d = await _llm(settings).route(skill_input("oi"), skill_options)
    assert d.choice == "__global__" and d.usage["attempts"] == 2 and route.call_count == 2


# ------------------------------------------------------------------ cache


@respx.mock
async def test_cache_hit_preserves_original_latency_and_cost(settings, skill_options, tmp_path):
    route = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=chat_completion(
        '{"choice": "trocas_devolucoes", "confidence": 0.7}', cost=0.0042)))
    cache = ResponseCache(str(tmp_path / "resp"))
    router = _llm(settings, cache=cache)
    inp = skill_input("o tenis veio errado")

    first = await router.route(inp, skill_options)
    second = await router.route(inp, skill_options)

    assert route.call_count == 1
    assert not first.cached and second.cached
    assert second.latency_ms == first.latency_ms
    assert second.cost_usd == first.cost_usd == pytest.approx(0.0042)
    assert second.choice == first.choice and second.usage == first.usage

    # different options -> different key -> new call
    await router.route(inp, skill_options[:3])
    assert route.call_count == 2
    # other namespace (e.g. repetition) -> miss
    other = _llm(settings, cache=ResponseCache(str(tmp_path / "resp"), namespace="rep=2"))
    await other.route(inp, skill_options)
    assert route.call_count == 3


# ------------------------------------------------------------------ jev


@respx.mock
async def test_jev_records_served_model_and_sends_no_params(settings, skill_options):
    route = respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=chat_completion(
        'Sure! ```json\n{"choice": "pedidos_logistica", "confidence": 0.99}\n```',
        model="openai/gpt-6-luna", provider="OpenAI", cost=2.17e-05)))
    d = await _jev(settings).route(skill_input("cade minha encomenda"), skill_options)

    assert d.choice == "pedidos_logistica" and d.confidence == pytest.approx(0.99)
    assert d.usage["served_model"] == "openai/gpt-6-luna" and d.usage["provider"] == "OpenAI"
    assert d.cost_usd == pytest.approx(2.17e-05)
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "typesafe/jev-router"
    for p in ("temperature", "seed", "response_format"):
        assert p not in body
    assert "ONLY a JSON object" in body["messages"][0]["content"]


@respx.mock
async def test_jev_retries_once_on_unparseable_then_succeeds(settings, skill_options):
    route = respx.post(CHAT_URL).mock(side_effect=[
        httpx.Response(200, json=chat_completion("I think it is about shipping.",
                                                 model="m/one", cost=1e-5)),
        httpx.Response(200, json=chat_completion('{"choice":"pedidos_logistica","confidence":0.8}',
                                                 model="m/two", cost=2e-5)),
    ])
    d = await _jev(settings).route(skill_input("cade"), skill_options)
    assert route.call_count == 2
    assert d.choice == "pedidos_logistica"
    assert d.cost_usd == pytest.approx(3e-5)  # both calls are paid
    assert d.usage["served_models"] == ["m/one", "m/two"]
    assert d.usage["parse_retries_used"] == 1
    retry_msgs = json.loads(route.calls.last.request.content)["messages"]
    assert retry_msgs[-2]["role"] == "assistant" and "Invalid answer" in retry_msgs[-1]["content"]


@respx.mock
async def test_jev_parse_failure_abstains(settings, skill_options):
    respx.post(CHAT_URL).mock(return_value=httpx.Response(
        200, json=chat_completion("no idea", cost=1e-5)))
    d = await _jev(settings).route(skill_input("???"), skill_options)
    assert d.choice is None and d.confidence == 0.0
    assert d.usage["parse_fail"] is True and d.usage["calls"] == 2
    assert d.cost_usd == pytest.approx(2e-5)


@pytest.mark.parametrize(
    ("text", "choice", "conf"),
    [
        ('{"choice": "pedidos_logistica", "confidence": 0.9}', "pedidos_logistica", 0.9),
        ('```json\n{"choice":"__global__","confidence":0.7}\n```', "__global__", 0.7),
        ("Answer: {'choice': 'trocas_devolucoes', 'confidence': 0.6} done",
         "trocas_devolucoes", 0.6),
        ('{"choice": "Pagamentos_Reembolsos", "confidence": "85%"}',
         "pagamentos_reembolsos", 0.85),
        ('{"choice": "pedidos_logistica", "confidence": 90}', "pedidos_logistica", 0.9),
        ('{"choice": "pedidos_logistica"}', "pedidos_logistica", None),
        ('choice: trocas_devolucoes, confidence: 0.55', "trocas_devolucoes", 0.55),
        ("  __global__ ", "__global__", None),
        ('{"choice": "inexistente", "confidence": 0.9}', None, None),
        ("", None, None),
        ('{"choice": "pedidos_logistica", "confidence": 1.7}', "pedidos_logistica", 0.017),
    ],
)
def test_jev_parser_tolerance(text, choice, conf):
    got_choice, got_conf = parse_choice(text, IDS)
    assert got_choice == choice
    if conf is None:
        assert got_conf is None
    else:
        assert got_conf == pytest.approx(conf)
