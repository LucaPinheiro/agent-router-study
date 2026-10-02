"""F9 (router parts): Jev corrective retry keeps the ranking request, ranked-reply regex
fallback, response-cache key covers every generation param actually sent."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from router_helpers import BASE_URL, chat_completion

from routing_study.llm import make_bedrock_chat, make_chat_model, make_ollama_chat
from routing_study.routers.base import RoutingInput
from routing_study.routers.jev import _CORRECTION, JevRouter, parse_ranked_reply
from routing_study.routers.llm import chat_params
from routing_study.settings import ReasoningPrefs

CHAT_URL = f"{BASE_URL}/chat/completions"
IDS = ["pedidos_logistica", "pagamentos_reembolsos", "trocas_devolucoes"]


def _jev(settings, variant: str = "P0") -> JevRouter:
    model = "typesafe/jev-router"
    chat = make_chat_model(
        settings, model, supported_parameters=[], http_async_client=httpx.AsyncClient()
    )
    return JevRouter(chat, settings, model=model, prompt_variant=variant)


def _tool() -> RoutingInput:
    return RoutingInput(message="x", level="tool", loaded_skill="s")


# ------------------------------------------------------------------ Jev corrective retry


@pytest.mark.parametrize(
    ("variant", "reply", "marker"),
    [
        ("P0", '{"choice": "trocas_devolucoes", "confidence": 0.8, "ranking": []}', '"ranking"'),
        ("P6c", '{"ranking": ["trocas_devolucoes"], "confidence": 0.8}', '"ranking": [<up to'),
        ("P6", '{"ranking": [{"id": "trocas_devolucoes", "score": 0.8}]}', '"score"'),
    ],
)
@respx.mock
async def test_tool_stage_correction_keeps_asking_for_the_ranking(
    settings, skill_options, variant, reply, marker
):
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=chat_completion("hmm, not sure")),
            httpx.Response(200, json=chat_completion(reply)),
        ]
    )
    d = await _jev(settings, variant).route(_tool(), skill_options)
    assert d.choice == "trocas_devolucoes"
    correction = json.loads(route.calls.last.request.content)["messages"][-1]["content"]
    assert correction.startswith("Invalid answer.") and marker in correction


def test_skill_stage_correction_and_cache_key_are_unchanged(settings, skill_options):
    jev = _jev(settings)
    skill = RoutingInput(message="x", level="skill")
    assert jev.cache_params(skill, skill_options)["correction"] == _CORRECTION
    assert jev.cache_params(_tool(), skill_options)["correction"] != _CORRECTION


@pytest.mark.parametrize(
    "text",
    [
        '{"ranking": ["pedidos_logistica", "trocas_devolucoes"',  # cut mid-object
        "ranking: [pedidos_logistica, trocas_devolucoes], confidence: 0.7",
        '```json\n{"ranking": [pedidos_logistica, trocas_devolucoes], "confidence": 0.7}\n```',
    ],
)
def test_ranked_reply_regex_fallback_keeps_ids_in_order(text):
    choice, _, _, others = parse_ranked_reply(text, IDS)
    assert choice == "pedidos_logistica"
    assert [c for c, _ in others] == ["trocas_devolucoes"]


def test_ranked_reply_fallback_reads_the_confidence_and_ignores_prose():
    choice, conf, _, _ = parse_ranked_reply("ranking: [trocas_devolucoes] confidence: 0.7", IDS)
    assert (choice, conf) == ("trocas_devolucoes", 0.7)
    assert parse_ranked_reply("I think it is about shipping.", IDS)[0] is None


# ------------------------------------------------------------------ cache key params


def test_cache_key_covers_ollama_thinking_and_logprobs(settings):
    off = make_ollama_chat(settings, "qwen3:8b", temperature=0, max_tokens=64)
    on = make_ollama_chat(
        settings, "qwen3:8b", temperature=0, max_tokens=64, reasoning=ReasoningPrefs(effort="low")
    )
    lp = make_ollama_chat(settings, "qwen3:8b", temperature=0, max_tokens=64, logprobs=True)
    assert chat_params(off) != chat_params(on)
    assert chat_params(off)["reasoning_effort"] == "none"
    assert chat_params(lp)["logprobs"] is True and chat_params(off) != chat_params(lp)


def test_cache_key_of_openrouter_and_bedrock_is_unchanged(settings):
    """Params already covered stay the legacy 5 keys: existing paid cache entries still hit."""
    legacy = ("model_name", "temperature", "seed", "max_tokens", "extra_body")
    jev = make_chat_model(settings, "typesafe/jev-router", supported_parameters=[])
    sonnet = make_chat_model(settings, "anthropic/claude-sonnet-5", temperature=0, max_tokens=256)
    bedrock = make_bedrock_chat(settings, "global.anthropic.claude-sonnet-5", max_tokens=256)
    for chat in (jev, sonnet, bedrock):
        assert tuple(chat_params(chat)) == legacy
    assert chat_params(bedrock)["max_tokens"] == 256


def test_verbose_tool_reply_with_a_broken_object_keeps_the_ranking_ids():
    from routing_study.routers.jev import parse_ranking, parse_reply

    text = (
        '{"choice": "pedidos_logistica", "confidence": 0.8, "ranking": '
        '[{"id": "trocas_devolucoes", "confidence": 0.1}, {"id": "pagamentos_reembolsos"'
    )
    assert parse_reply(text, IDS)[0] == "pedidos_logistica"
    ranked = [c for c, _ in parse_ranking(text, IDS)]
    assert ranked == ["trocas_devolucoes", "pagamentos_reembolsos"]
