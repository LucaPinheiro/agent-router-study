"""Regex, BM25, embedding and hybrid routers (no network)."""

from __future__ import annotations

import pytest
from router_helpers import FakeEmbedder, skill_input

from routing_study.routers.bm25 import BM25Router
from routing_study.routers.embedding import EmbeddingRouter
from routing_study.routers.hybrid import HybridRouter
from routing_study.routers.regex import RegexRouter, RegexRules

RULES = RegexRules.model_validate(
    {
        "full_score": 1.0,
        "rules": {
            "pedidos_logistica": [
                {"pattern": r"\bencomenda\b", "weight": 1.0},
                {"pattern": r"\bpedido\b", "weight": 0.3},
            ],
            "pagamentos_reembolsos": [
                {"pattern": r"\breembolso\b", "weight": 1.0},
                {"pattern": r"dinheiro de volta", "weight": 0.6},
            ],
            "__global__": [{"pattern": r"\batendente\b", "weight": 1.0}],
        },
    }
)


# ------------------------------------------------------------------ regex


async def test_regex_strong_single_match_full_confidence(skill_options):
    d = await RegexRouter(RULES).route(skill_input("Cadê minha ENCOMENDA?"), skill_options)
    assert d.choice == "pedidos_logistica"
    assert d.confidence == pytest.approx(1.0)
    assert d.strategy == "regex" and d.cost_usd == 0.0 and d.latency_ms > 0


async def test_regex_no_match_abstains(skill_options):
    d = await RegexRouter(RULES).route(skill_input("bom dia"), skill_options)
    assert d.choice is None and d.confidence == 0.0


async def test_regex_accent_insensitive_and_global_option(skill_options):
    rules = RegexRules.model_validate(
        {"rules": {"trocas_devolucoes": [{"pattern": r"devolução", "weight": 1.0}]}}
    )
    d = await RegexRouter(rules).route(skill_input("quero fazer a DEVOLUCAO"), skill_options)
    assert d.choice == "trocas_devolucoes"
    d = await RegexRouter(RULES).route(skill_input("falar com atendente"), skill_options)
    assert d.choice == "__global__"


async def test_regex_competing_matches_reduce_confidence(skill_options):
    d = await RegexRouter(RULES).route(
        skill_input("quero meu dinheiro de volta do pedido"), skill_options
    )
    # 0.6 vs 0.3 -> strength 0.6, separation 0.5 -> 0.6 * 0.75
    assert d.choice == "pagamentos_reembolsos"
    assert d.confidence == pytest.approx(0.45)
    assert [c for c, _ in d.candidates] == ["pagamentos_reembolsos", "pedidos_logistica"]


async def test_regex_tie_halves_confidence(skill_options):
    d = await RegexRouter(RULES).route(skill_input("reembolso da encomenda"), skill_options)
    assert d.confidence == pytest.approx(0.5)


async def test_regex_only_scores_offered_options(skill_options):
    d = await RegexRouter(RULES).route(skill_input("encomenda"), skill_options[1:])
    assert d.choice is None


def test_project_rules_file_compiles():
    router = RegexRouter.from_path("config/regex_rules.yaml")
    ids = set(router.rules.rules)
    assert {"pedidos_logistica", "pagamentos_reembolsos", "trocas_devolucoes", "__global__"} <= ids
    assert len(ids) == 4 + 18


# ------------------------------------------------------------------ bm25


async def test_bm25_picks_lexical_best_with_margin_confidence(skill_options):
    d = await BM25Router().route(skill_input("segunda via do boleto"), skill_options)
    assert d.choice == "pagamentos_reembolsos"
    assert 0.0 < d.confidence <= 1.0
    s1, s2 = d.candidates[0][1], d.candidates[1][1]
    assert d.confidence == pytest.approx((s1 - max(s2, 0)) / s1, abs=1e-3)


async def test_bm25_abstains_without_overlap(skill_options):
    d = await BM25Router().route(skill_input("xyzzy qwerty"), skill_options)
    assert d.choice is None


# ------------------------------------------------------------------ embedding


async def test_embedding_max_example_and_vector_cache(skill_options, tmp_path):
    emb = FakeEmbedder()
    router = EmbeddingRouter(emb, vector_cache_dir=str(tmp_path / "vec"))
    d = await router.route(skill_input("o tenis veio no tamanho errado"), skill_options)
    assert d.choice == "trocas_devolucoes"
    assert d.usage["served_model"] == "Fake/Embed" and d.usage["provider"] == "FakeProvider"
    assert d.cost_usd == pytest.approx(1e-6)  # only the query counts per request
    assert d.usage["index_cost_usd"] > 0
    assert len(emb.calls) == 2  # option index + query

    # new router instance, same disk cache: options are NOT re-embedded
    emb2 = FakeEmbedder()
    router2 = EmbeddingRouter(emb2, vector_cache_dir=str(tmp_path / "vec"))
    d2 = await router2.route(skill_input("quero meu reembolso"), skill_options)
    assert d2.choice == "pagamentos_reembolsos"
    assert emb2.calls == [["quero meu reembolso"]]
    assert d2.usage["index_cost_usd"] == 0.0


async def test_embedding_margin_vs_softmax_confidence(skill_options):
    msg = skill_input("segunda via do boleto")
    soft = await EmbeddingRouter(FakeEmbedder(), confidence="softmax").route(msg, skill_options)
    marg = await EmbeddingRouter(FakeEmbedder(), confidence="margin", margin_scale=0.1).route(
        msg, skill_options
    )
    assert soft.choice == marg.choice == "pagamentos_reembolsos"
    gap = marg.candidates[0][1] - marg.candidates[1][1]
    assert marg.confidence == pytest.approx(min(1.0, gap / 0.1), abs=1e-3)
    assert 0.25 < soft.confidence <= 1.0


async def test_embedding_centroid_mode(skill_options):
    d = await EmbeddingRouter(FakeEmbedder(), similarity="centroid").route(
        skill_input("quero rastrear meu pacote"), skill_options
    )
    assert d.choice == "pedidos_logistica"


# ------------------------------------------------------------------ hybrid


async def test_hybrid_rrf_agreement(skill_options):
    router = HybridRouter(BM25Router(), EmbeddingRouter(FakeEmbedder()), rrf_k=60)
    d = await router.route(skill_input("segunda via do boleto"), skill_options)
    assert d.choice == "pagamentos_reembolsos"
    assert d.usage["bm25_choice"] == d.usage["embedding_choice"] == "pagamentos_reembolsos"
    assert d.candidates[0][1] == pytest.approx(2 / 61, abs=1e-6)
    assert d.cost_usd > 0 and 0 < d.confidence <= 1


async def test_embedding_response_cache_keyed_by_router_config(skill_options, tmp_path):
    from routing_study.routers.common import ResponseCache

    inp = skill_input("quero meu reembolso")
    emb = FakeEmbedder()
    await EmbeddingRouter(emb, cache=ResponseCache(str(tmp_path / "r"))).route(inp, skill_options)
    hit = await EmbeddingRouter(emb, cache=ResponseCache(str(tmp_path / "r"))).route(
        inp, skill_options
    )
    assert hit.cached
    miss = await EmbeddingRouter(
        emb, confidence="margin", cache=ResponseCache(str(tmp_path / "r"))
    ).route(inp, skill_options)
    assert not miss.cached


async def test_regex_weight_sums_are_exact_at_thresholds(skill_options):
    """B5: 0.6 + 0.3 must reach full_score 0.9 (float sum is 0.8999…)."""
    rules = RegexRules.model_validate(
        {
            "full_score": 0.9,
            "rules": {
                "pagamentos_reembolsos": [
                    {"pattern": r"\breembolso\b", "weight": 0.6},
                    {"pattern": r"\bpix\b", "weight": 0.3},
                ]
            },
        }
    )
    d = await RegexRouter(rules).route(skill_input("reembolso via pix"), skill_options)
    assert d.confidence == 1.0
    assert d.candidates == [("pagamentos_reembolsos", 0.9)]


async def test_hybrid_propagates_cached_flag_and_original_timing(skill_options, tmp_path):
    """B7: a cached embedding sub-decision makes the hybrid decision cached, with its timing."""
    import asyncio

    from routing_study.routers.common import ResponseCache

    class Slow(FakeEmbedder):
        async def embed(self, texts):
            await asyncio.sleep(0.05)
            return await super().embed(texts)

    emb = EmbeddingRouter(Slow(), cache=ResponseCache(str(tmp_path / "r")))
    router = HybridRouter(BM25Router(), emb)
    inp = skill_input("segunda via do boleto")
    first = await router.route(inp, skill_options)
    second = await router.route(inp, skill_options)
    assert not first.cached and second.cached
    assert second.cost_usd == first.cost_usd > 0
    assert second.latency_ms == pytest.approx(first.latency_ms) and second.latency_ms >= 50
