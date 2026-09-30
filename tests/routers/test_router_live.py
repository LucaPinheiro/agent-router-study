"""Live smoke tests, one per provider: Bedrock (Sonnet 5 + Haiku 4.5), Ollama (chat + embed),
OpenRouter (Jev). Tiny calls (max_tokens <= 64); Bedrock/OpenRouter cost real money and are
recorded in the spend ledger."""

from __future__ import annotations

import uuid

import httpx
import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from routing_study.llm import chat_model_for, extract_call_usage, validate_models
from routing_study.routers.base import RouteOption, RoutingInput
from routing_study.routers.pipeline import build_routers
from routing_study.settings import load_settings

pytestmark = pytest.mark.integration

OPTIONS = [
    RouteOption(
        id="pedidos_logistica",
        description="Status, rastreio, endereco, reagendamento e cancelamento de pedidos",
        examples=["cade minha encomenda?", "quero rastrear meu pedido"],
    ),
    RouteOption(
        id="pagamentos_reembolsos",
        description="Pagamentos, 2a via de boleto, reembolsos e contestacao de cobrancas",
        examples=["preciso da 2a via do boleto", "quero meu reembolso"],
    ),
    RouteOption(
        id="trocas_devolucoes",
        description="Elegibilidade de devolucao, devolucao, etiqueta, troca e garantia",
        examples=["o tenis veio no tamanho errado", "quero devolver o produto"],
    ),
]
INP = RoutingInput(message="Preciso da segunda via do boleto, venceu ontem", level="skill")
MAX_TOKENS = 64


def _show(name: str, d) -> None:
    print(
        f"\n[{name}] choice={d.choice} conf={d.confidence:.2f} cost_usd={d.cost_usd:.8f} "
        f"latency_ms={d.latency_ms:.0f} served={d.usage.get('served_model')} "
        f"provider={d.usage.get('provider')} tokens={d.usage.get('prompt_tokens')}/"
        f"{d.usage.get('completion_tokens')} cache={d.usage.get('cache_read')}/"
        f"{d.usage.get('cache_write')} parse_fail={d.usage.get('parse_fail', False)}"
    )


def _ollama_up() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/tags", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.parametrize(
    "config", ["config/experiments/e5_llm_sonnet.yaml", "config/experiments/e6_llm_haiku.yaml"]
)
async def test_live_bedrock_router(config, tmp_path):
    s = load_settings(config, cache_dir=str(tmp_path))
    # Sonnet 5's forced tool-use reply is ~68 output tokens even for {choice, confidence}:
    # 64 truncates it (measured), so the Bedrock router smoke allows 96
    s.strategies.llm.max_tokens = 96
    d = await build_routers(s, {"llm"})["llm"].route(INP, OPTIONS)
    _show(s.strategies.llm.model, d)
    assert d.usage["provider"] == "bedrock" and d.usage["served_model"] == s.strategies.llm.model
    assert d.choice == "pagamentos_reembolsos" and d.cost_usd > 0


async def test_live_bedrock_prompt_cache_write_then_read():
    s = load_settings("config/experiments/e9_regex_jev_llm.yaml")
    s.executor.max_tokens = 16
    chat = chat_model_for(s, s.executor)
    # unique static prefix above the 1024-token cache minimum: call 1 writes, call 2 reads
    static = f"[{uuid.uuid4()}] " + "Seja cordial, objetivo e responda em portugues. " * 150
    msgs = [
        SystemMessage([{"type": "text", "text": static, "cache_control": {"type": "ephemeral"}}]),
        HumanMessage("diga oi"),
    ]
    first = extract_call_usage(await chat.ainvoke(msgs))
    second = extract_call_usage(await chat.ainvoke(msgs))
    print(f"\n[cache] first={first} \n[cache] second={second}")
    assert first["cache_write"] > 1024 and second["cache_read"] == first["cache_write"]
    assert second["cost_usd"] < first["cost_usd"]


async def test_live_ollama_chat_and_embed(tmp_path):
    if not _ollama_up():
        pytest.skip("ollama not running")
    s = load_settings("config/experiments/e6b_llm_qwen3_local.yaml", cache_dir=str(tmp_path))
    s.strategies.llm_local.max_tokens = MAX_TOKENS
    await validate_models(s, names={"llm_local", "embedding"})  # the local tags exist
    routers = build_routers(s, {"llm_local", "embedding"})
    for name in ("llm_local", "embedding"):
        d = await routers[name].route(INP, OPTIONS)
        _show(name, d)
        assert d.usage["provider"] == "ollama" and d.cost_usd == 0.0
        assert d.choice == "pagamentos_reembolsos"


async def test_live_openrouter_jev(tmp_path):
    s = load_settings("config/experiments/e9_regex_jev_llm.yaml", cache_dir=str(tmp_path))
    if not s.openrouter_api_key.get_secret_value():
        pytest.skip("OPENROUTER_API_KEY not set")
    s.strategies.jev.max_tokens = MAX_TOKENS
    s.strategies.jev.parse_retries = 0
    supported = await validate_models(s, names={"jev"})
    d = await build_routers(s, {"jev"}, supported_parameters=supported)["jev"].route(INP, OPTIONS)
    _show("jev", d)
    assert d.usage.get("served_model")
    assert d.cost_usd > 0, "OpenRouter usage.cost missing"
    assert d.choice == "pagamentos_reembolsos" or d.usage.get("parse_fail")
