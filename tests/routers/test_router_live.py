"""Live smoke test against OpenRouter (llm + jev routers, 3 options). Costs real money."""

from __future__ import annotations

import pytest

from routing_study.llm import validate_models
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


async def test_live_llm_and_jev_route(tmp_path):
    s = load_settings("config/experiments/e9_regex_jev_llm.yaml", cache_dir=str(tmp_path))
    if not s.openrouter_api_key.get_secret_value():
        pytest.skip("OPENROUTER_API_KEY not set")
    supported = await validate_models(s)
    routers = build_routers(s, {"llm", "jev"}, supported_parameters=supported)
    inp = RoutingInput(message="Preciso da segunda via do boleto, venceu ontem", level="skill")
    for name in ("llm", "jev"):
        d = await routers[name].route(inp, OPTIONS)
        print(
            f"\n[{name}] model={routers[name].model} choice={d.choice} conf={d.confidence:.2f} "
            f"cost_usd={d.cost_usd:.8f} latency_ms={d.latency_ms:.0f} "
            f"served={d.usage.get('served_model')} provider={d.usage.get('provider')} "
            f"calls={d.usage.get('calls')} parse_fail={d.usage.get('parse_fail', False)}"
        )
        assert d.usage.get("served_model")
        assert d.cost_usd > 0, "OpenRouter usage.cost missing"
        assert d.choice == "pagamentos_reembolsos" or d.usage.get("parse_fail")
