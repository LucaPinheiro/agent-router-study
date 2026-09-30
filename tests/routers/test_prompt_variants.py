"""Router prompt variants (docs/prompt-apex.md): variant parsing, catalog-derived guide and
shots, output formats (verbose / compact / scored) for the LLM and Jev routers."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastmcp import Client
from pydantic import ValidationError
from router_helpers import BASE_URL, chat_completion

from routing_study.catalog import Catalog, fetch_catalog
from routing_study.llm import make_chat_model
from routing_study.prompts.routers import PromptSpec, parse_variant
from routing_study.routers.base import GLOBAL_OPTION, RoutingInput
from routing_study.routers.jev import JevRouter, parse_ranked_reply
from routing_study.routers.llm import (
    LLMRouter,
    build_messages,
    choice_probability,
    choice_schema,
    prompt_chars,
    read_choice,
    trim_ranking,
)
from routing_study.settings import LLMStrategy, Settings

CHAT_URL = f"{BASE_URL}/chat/completions"


@pytest.fixture(scope="module")
async def catalog() -> Catalog:
    from mcp_server.server import mcp

    return await fetch_catalog(Settings(_env_file=None), Client(mcp))


def _tool_input(msg: str = "quero trocar o tamanho") -> RoutingInput:
    return RoutingInput(message=msg, level="tool", loaded_skill="trocas_devolucoes")


def _system(messages) -> str:
    c = messages[0].content
    return c if isinstance(c, str) else c[0]["text"]


# ------------------------------------------------------------------ variants


def test_variant_tokens_compose_left_to_right():
    assert parse_variant("P0") == PromptSpec()
    spec = parse_variant("P0+P1+P2k2+P3+P4+P5+P6c+k2")
    assert spec == PromptSpec(
        language="pt",
        guide=True,
        shots=2,
        scope=True,
        rationale=True,
        output="compact",
        rank_k=2,
    )
    assert parse_variant("P6+P6c").output == "compact"  # later token wins
    with pytest.raises(ValueError, match="unknown prompt variant token"):
        parse_variant("P0+P9")


def test_settings_validate_the_variant_and_track():
    cfg = LLMStrategy(model="m", prompt_variant="P0+P1", prompt_track="tuned")
    assert cfg.prompt_variant == "P0+P1" and cfg.prompt_track == "tuned"
    with pytest.raises(ValidationError):
        LLMStrategy(model="m", prompt_variant="P7")
    with pytest.raises(ValidationError):
        LLMStrategy(model="m", prompt_track="best")


# ------------------------------------------------------------------ catalog data


async def test_avoid_clauses_come_verbatim_from_dont_use_for(catalog):
    clauses = dict(catalog.avoid_clauses("create_exchange"))
    assert clauses["dinheiro de volta (use create_return_request)"] == ["create_return_request"]
    opts = {o.id: o for o in catalog.skill_options()}
    # skill level: tool targets rewritten as skills, same-skill clauses dropped
    assert ("pedido já entregue (use trocas_devolucoes)", ["trocas_devolucoes"]) in opts[
        "pedidos_logistica"
    ].avoid
    assert all("pedidos_logistica" not in t for _, t in opts["pedidos_logistica"].avoid)
    assert opts[GLOBAL_OPTION].shots  # the global tools' catalog examples


async def test_prompt_only_fields_stay_out_of_dumps(catalog):
    opt = catalog.tool_options("trocas_devolucoes")[0]
    assert opt.avoid and opt.shots
    assert set(opt.model_dump()) == {"id", "description", "examples", "keywords"}


# ------------------------------------------------------------------ rendering


async def test_guide_lists_only_confusions_inside_the_option_set(catalog):
    opts = catalog.tool_options("trocas_devolucoes")
    system = _system(
        build_messages(
            _tool_input(),
            opts,
            history_turns=0,
            allow_abstain=False,
            json_reply=False,
            spec=parse_variant("P1"),
        )
    )
    guide = system.split("<guide>")[1]
    assert "- not create_exchange: dinheiro de volta (use create_return_request)" in guide
    assert "cancel_order" not in guide  # target outside this skill's tools
    p0 = build_messages(_tool_input(), opts, history_turns=0, allow_abstain=False, json_reply=False)
    assert "<guide>" not in _system(p0) and "<examples>" not in _system(p0)


async def test_shots_move_examples_into_demonstrations(catalog):
    opts = catalog.tool_options("trocas_devolucoes")
    first = opts[0].shots[0]
    system = _system(
        build_messages(
            _tool_input(),
            opts,
            history_turns=0,
            allow_abstain=False,
            json_reply=False,
            spec=parse_variant("P2k1"),
        )
    )
    options, demos = system.split("<examples>")
    assert f'- "{first}" -> {opts[0].id}' in demos
    assert first not in options  # shown once, as a demonstration
    assert demos.count('\n- "') == len(opts)


async def test_static_prefix_carries_rules_and_dynamic_part_the_message(catalog):
    msgs = build_messages(
        _tool_input("mensagem do cliente"),
        catalog.tool_options("trocas_devolucoes"),
        history_turns=0,
        allow_abstain=False,
        json_reply=True,
        model="global.anthropic.claude-sonnet-5",
        spec=parse_variant("P0+P3+P4+P6c"),
    )
    system = _system(msgs)
    assert msgs[0].content[0]["cache_control"] == {"type": "ephemeral"}
    assert "mensagem do cliente" not in system and "mensagem do cliente" in msgs[1].content
    assert "Pick a specific action" in system and "`rationale`" in system
    assert '"ranking": [<up to 3 of [' in system
    static, dynamic = prompt_chars(msgs)
    assert static == len(system) and dynamic == len(msgs[1].content)


async def test_pt_variant_translates_the_instructions(catalog):
    system = _system(
        build_messages(
            _tool_input(),
            catalog.tool_options("trocas_devolucoes"),
            history_turns=0,
            allow_abstain=True,
            json_reply=False,
            spec=parse_variant("P5"),
        )
    )
    assert system.startswith("Você encaminha") and "`__abstain__`" in system


# ------------------------------------------------------------------ output formats


def test_output_formats_schemas_and_readers():
    ids = ["a", "b", "c", "d"]
    compact = choice_schema(ids, ids, parse_variant("P6c+k2"))
    js = compact.model_json_schema()
    assert js["properties"]["ranking"]["maxItems"] == 2
    got = compact.model_validate({"ranking": ["b", "a"], "confidence": 0.8})
    assert read_choice(got) == ("b", 0.8, [("a", 0.0)])

    scored = choice_schema(ids, ids, parse_variant("P6+P4"))
    assert list(scored.model_json_schema()["properties"]) == ["rationale", "ranking"]
    got = scored.model_validate(
        {"rationale": "x", "ranking": [{"id": "c", "score": 0.7}, {"id": "a", "score": 0.2}]}
    )
    assert read_choice(got) == ("c", 0.7, [("a", 0.2)])
    assert read_choice(compact.model_construct(ranking=[], confidence=0.5)) is None

    skill = choice_schema(ids, None, parse_variant("P6c"))  # skill stage: always a choice
    assert set(skill.model_json_schema()["properties"]) == {"choice", "confidence"}
    assert trim_ranking({"ranking": [1, 2, 3, 4]}, 2) == {"ranking": [1, 2]}
    assert trim_ranking({"choice": "a", "ranking": [1, 2, 3]}, 1)["ranking"] == [1, 2, 3]


def test_logprob_confidence_reads_the_first_ranked_id():
    from langchain_core.messages import AIMessage

    toks = ['{"', "ranking", '":', ' ["', "b", '",', ' "', "a", '"]}']
    lps = [0.0, 0.0, 0.0, 0.0, -0.1, 0.0, 0.0, -2.0, 0.0]
    raw = AIMessage(
        "",
        response_metadata={
            "logprobs": {
                "content": [{"token": t, "logprob": lp} for t, lp in zip(toks, lps, strict=True)]
            }
        },
    )
    assert choice_probability(raw, "b") == pytest.approx(0.904837, rel=1e-4)


@respx.mock
async def test_llm_router_compact_ranking_becomes_candidates(settings):
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json=chat_completion(
                '{"ranking": ["create_exchange", "check_return_eligibility"], "confidence": 0.9}'
            ),
        )
    )
    model = "anthropic/claude-haiku-4.5"
    chat = make_chat_model(
        settings, model, temperature=0, max_tokens=256, http_async_client=httpx.AsyncClient()
    )
    router = LLMRouter(chat, settings, model=model, prompt_variant="P0+P6c")
    from routing_study.routers.base import RouteOption

    opts = [
        RouteOption(id=i, description=i)
        for i in ("create_exchange", "check_return_eligibility", "escalate_to_human")
    ]
    d = await router.route(_tool_input(), opts)
    assert d.choice == "create_exchange" and d.confidence == pytest.approx(0.9)
    assert d.candidates == [("create_exchange", 0.9), ("check_return_eligibility", 0.0)]
    assert d.usage["static_chars"] > d.usage["dynamic_chars"] > 0
    schema = json.loads(route.calls.last.request.content)["response_format"]["json_schema"]
    assert schema["schema"]["properties"]["ranking"]["items"]["enum"] == [o.id for o in opts]


# ------------------------------------------------------------------ jev


def test_jev_parses_compact_scored_and_fallback_replies():
    valid = ["a", "b", "c"]
    assert parse_ranked_reply(
        '```json\n{"ranking": ["b", "x", "a"], "confidence": 0.7}\n```', valid
    ) == (
        "b",
        0.7,
        0.7,
        [("a", 0.0)],
    )
    scored = '{"ranking": [{"id": "c", "score": 0.6}, {"id": "b", "score": 0.3}]}'
    assert parse_ranked_reply(scored, valid) == ("c", 0.6, 0.6, [("b", 0.3)])
    fallback = parse_ranked_reply('{"choice": "a", "confidence": 0.5}', valid)
    assert fallback[:2] == ("a", 0.5)
    assert parse_ranked_reply('{"ranking": ["x"]}', valid)[0] is None


@respx.mock
async def test_jev_router_ranked_variant(settings):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200, json=chat_completion('{"ranking": ["b", "a"], "confidence": 0.8}')
        )
    )
    model = "typesafe/jev-router"
    chat = make_chat_model(
        settings, model, supported_parameters=[], http_async_client=httpx.AsyncClient()
    )
    from routing_study.routers.base import RouteOption

    opts = [RouteOption(id=i, description=i) for i in ("a", "b")]
    d = await JevRouter(chat, settings, model=model, prompt_variant="P6c").route(
        _tool_input(), opts
    )
    assert d.choice == "b" and d.candidates == [("b", 0.8), ("a", 0.0)]
