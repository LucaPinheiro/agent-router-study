from __future__ import annotations

import pytest
from router_helpers import BASE_URL

from routing_study.routers.base import RouteOption
from routing_study.settings import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        openrouter_api_key="test-key",
        openrouter_base_url=BASE_URL,
        cache_dir=str(tmp_path / "cache"),
        http_retries=2,
    )


@pytest.fixture
def skill_options() -> list[RouteOption]:
    return [
        RouteOption(
            id="pedidos_logistica",
            description="Pedidos, entrega, rastreio, endereco e cancelamento de pedidos",
            examples=[
                "cade minha encomenda",
                "quero rastrear meu pacote",
                "mudar endereco de entrega",
            ],
            keywords=["entrega", "rastreio"],
        ),
        RouteOption(
            id="pagamentos_reembolsos",
            description="Pagamentos, boletos, reembolsos e contestacao de cobrancas",
            examples=["segunda via do boleto", "quero meu reembolso", "fui cobrado duas vezes"],
            keywords=["boleto", "reembolso"],
        ),
        RouteOption(
            id="trocas_devolucoes",
            description="Trocas, devolucoes, etiquetas de postagem e garantia",
            examples=[
                "o tenis veio no tamanho errado",
                "quero devolver o produto",
                "acionar garantia",
            ],
            keywords=["troca", "devolucao"],
        ),
        RouteOption(
            id="__global__",
            description="Perfil do cliente, central de ajuda e falar com atendente humano",
            examples=["falar com um atendente", "quais sao meus dados cadastrais"],
        ),
    ]


def pytest_collection_modifyitems(config, items):
    """Live tests run only when explicitly selected with `-m integration`."""
    if "integration" in (config.getoption("markexpr") or ""):
        return
    skip = pytest.mark.skip(reason="live test: run with -m integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
