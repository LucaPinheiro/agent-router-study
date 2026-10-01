"""Phase 2 non-LLM routers: utterance BM25, char n-grams, embedding top-k vote / history /
query cache, Platt + logistic, hybrid convex/stacker fusion, deferral scorer, classifier."""

from __future__ import annotations

import pytest
from router_helpers import FakeEmbedder, skill_input

from routing_study.routers.base import Message, RouteDecision, RouteOption, RoutingInput
from routing_study.routers.bm25 import BM25Router
from routing_study.routers.calibration import (
    LogisticModel,
    brier,
    fit_logistic,
    fit_platt,
)
from routing_study.routers.classifier import ClassifierRouter
from routing_study.routers.common import (
    char_ngrams,
    description_quotes,
    description_sentences,
    option_utterances,
    tokenize,
)
from routing_study.routers.embedding import EmbeddingRouter
from routing_study.routers.hybrid import (
    HybridRouter,
    deferral_features,
    fit_deferral,
    option_distribution,
    stack_feature_names,
    stack_features,
)
from routing_study.routers.pipeline import build_routers
from routing_study.settings import HybridStrategy, StrategiesConfig

DESC = (
    'Cancela um pedido. Irreversível.\nWHEN TO USE: "não quero mais, anula", desistência.\n'
    "PARAMETERS: order_id opcional."
)


# ------------------------------------------------------------------ text helpers


def test_description_sentences_drop_parameters_and_label():
    sents = description_sentences(DESC)
    assert "Cancela um pedido." in sents and "Irreversível." in sents
    assert not any("PARAMETERS" in s or "order_id" in s or "WHEN TO USE" in s for s in sents)
    assert description_quotes(DESC) == ["não quero mais, anula"]


def test_option_utterances_expansion_is_catalog_only_and_deduplicated():
    opt = RouteOption(
        id="x",
        description=DESC,
        examples=["cancela a compra"],
        keywords=["cancelar", "anular"],
        shots=["cancela a compra", "desisti do pedido"],
    )
    base = option_utterances(opt)
    assert base[0] == "cancela a compra" and "cancelar anular" in base
    assert "desisti do pedido" not in base
    full = option_utterances(opt, shots=True, quotes=True)
    assert "desisti do pedido" in full and "não quero mais, anula" in full
    assert len(full) == len(set(full))


def test_char_ngrams_and_accent_switch():
    grams = char_ngrams("Tá", 2, 3)
    assert " ta" in grams and "ta " in grams
    assert " tá" in char_ngrams("Tá", 2, 3, fold_accents=False)
    assert tokenize("devolução não", fold_accents=False) == ["devolução"]  # stopword folded
    assert tokenize("devolução não") == ["devolucao"]


# ------------------------------------------------------------------ BM25


async def test_bm25_utterance_index_max_and_topk(skill_options):
    msg = skill_input("quero rastrear meu pacote")
    for agg in ("max", "topk_sum"):
        d = await BM25Router(variant="l", index="utterance", aggregate=agg).route(
            msg, skill_options
        )
        assert d.choice == "pedidos_logistica"
    r = BM25Router(index="utterance")
    idx, owner = r._bm25(skill_options)
    assert len(owner) > len(skill_options)  # one document per utterance


async def test_bm25_char_analyzer_survives_typos(skill_options):
    d = await BM25Router(analyzer="char", variant="l").route(
        skill_input("rastreiar o pacotinho"), skill_options
    )
    assert d.choice == "pedidos_logistica"


async def test_bm25_shots_expansion_changes_the_index(skill_options):
    opts = [o.model_copy(update={"shots": ["onde anda o caminhao"]}) for o in skill_options[:1]]
    opts += skill_options[1:]
    plain = BM25Router(variant="l").scores("caminhao", opts)
    assert plain == []
    assert BM25Router(variant="l", shots=True).scores("caminhao", opts)[0][0] == opts[0].id


# ------------------------------------------------------------------ embedding


async def test_embedding_topk_vote_and_history(skill_options):
    r = EmbeddingRouter(FakeEmbedder(), similarity="topk_vote", top_k=3)
    d = await r.route(skill_input("quero meu reembolso"), skill_options)
    assert d.choice == "pagamentos_reembolsos"
    inp = RoutingInput(
        message="sim",
        level="skill",
        history=[Message(role="user", content="segunda via do boleto")],
    )
    plain = EmbeddingRouter(FakeEmbedder())
    with_hist = EmbeddingRouter(FakeEmbedder(), history_turns=1)
    assert with_hist.query_string(inp) == "segunda via do boleto\nsim"
    assert plain.query_string(inp) == "sim"
    assert (await with_hist.route(inp, skill_options)).choice == "pagamentos_reembolsos"


async def test_embedding_query_vector_cache_keeps_original_latency(tmp_path, skill_options):
    emb = FakeEmbedder()
    a = EmbeddingRouter(emb, vector_cache_dir=str(tmp_path / "v"))
    d1 = await a.route(skill_input("quero meu reembolso"), skill_options)
    n_calls = len(emb.calls)
    b = EmbeddingRouter(emb, vector_cache_dir=str(tmp_path / "v"), similarity="centroid")
    d2 = await b.route(skill_input("quero meu reembolso"), skill_options)
    assert len(emb.calls) == n_calls  # nothing re-embedded
    assert d2.cached and not d1.cached
    assert d2.usage["query_vector_cached"] and d2.latency_ms >= 1.0  # FakeEmbedder: 1 ms


def test_embedding_cache_params_unchanged_for_original_knobs(skill_options):
    r = EmbeddingRouter(FakeEmbedder())
    keys = set(r.cache_params(skill_input("x"), skill_options))
    assert keys == {
        "model",
        "similarity",
        "confidence",
        "softmax_temperature",
        "margin_scale",
        "provider",
        "query_instruction",
    }


# ------------------------------------------------------------------ calibration / logistic


def test_platt_is_monotone_and_beats_constant_on_separable_scores():
    xs = [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9] * 5
    ys = [0, 0, 0, 1, 0, 1, 1, 1] * 5
    cal = fit_platt(xs, ys)
    assert all(b >= a for a, b in zip(cal.y, cal.y[1:], strict=False))
    assert cal(0.9) > cal(0.1)
    assert brier([cal(x) for x in xs], ys) < brier([0.5] * len(xs), ys)
    assert cal(0.0) == 0.0  # sentinel kept


def test_logistic_model_fits_and_roundtrips():
    rows = [{"a": float(i % 2), "b": 0.0} for i in range(40)]
    ys = [i % 2 for i in range(40)]
    m = fit_logistic(rows, ys, ["a", "b"], l2=0.1)
    assert m({"a": 1.0}) > 0.9 and m({"a": 0.0}) < 0.1
    assert LogisticModel.model_validate(m.model_dump())({"a": 1.0}) == pytest.approx(m({"a": 1.0}))


# ------------------------------------------------------------------ hybrid


def _dec(choice: str | None, conf: float, cands: list[tuple[str, float]]) -> RouteDecision:
    return RouteDecision(choice=choice, confidence=conf, candidates=cands, strategy="x")


def test_option_distribution_uses_calibrated_top_and_raw_rest():
    d = option_distribution(_dec("a", 0.6, [("a", 3.0), ("b", 1.0), ("c", 0.0)]), ["a", "b", "c"])
    assert d["a"] == pytest.approx(0.6) and d["b"] == pytest.approx(0.4) and d["c"] == 0.0
    assert option_distribution(_dec(None, 0.0, []), ["a", "b"]) == {"a": 0.5, "b": 0.5}


async def test_hybrid_convex_alpha_extremes_follow_one_member(skill_options):
    bm25, emb = BM25Router(variant="l"), EmbeddingRouter(FakeEmbedder())
    msg = skill_input("segunda via do boleto")
    lex = await bm25._route(msg, skill_options)
    sparse = await HybridRouter(bm25, emb, fusion="convex", alpha=1.0)._route(msg, skill_options)
    assert sparse.choice == lex.choice
    assert sparse.confidence == pytest.approx(lex.confidence)
    dense = await HybridRouter(bm25, emb, fusion="convex", alpha=0.0)._route(msg, skill_options)
    assert dense.choice == (await emb._route(msg, skill_options)).choice


async def test_hybrid_stacker_scores_options(skill_options):
    members = ["bm25", "embedding"]
    names = stack_feature_names(members)
    w = [0.0] * len(names)
    w[names.index("agree")] = 4.0
    model = LogisticModel(features=names, weights=w, bias=-2.0)
    router = HybridRouter(
        BM25Router(variant="l"),
        EmbeddingRouter(FakeEmbedder()),
        fusion="stacker",
        stacker={"skill": model},
    )
    d = await router.route(skill_input("quero meu reembolso"), skill_options)
    assert d.choice == "pagamentos_reembolsos" and d.confidence == pytest.approx(
        model({"agree": 1})
    )
    feats = stack_features({"bm25": d, "embedding": d}, [o.id for o in skill_options])
    assert feats["pagamentos_reembolsos"]["unanimous"] == 1.0
    with pytest.raises(ValueError):
        HybridRouter(BM25Router(), EmbeddingRouter(FakeEmbedder()), fusion="stacker")
    with pytest.raises(ValueError):
        HybridStrategy(fusion="stacker")


def test_deferral_features_and_fit():
    a = _dec("x", 0.9, [("x", 2.0), ("y", 1.0)])
    b = {"choice": "x", "confidence": 0.5, "candidates": [["x", 0.7], ["y", 0.6]]}
    f = deferral_features({"regex": None, "bm25": a, "embedding": b}, turns=3)
    assert f["abstain_regex"] == 1.0 and f["conf_bm25"] == 0.9
    assert f["agree_bm25_embedding"] == 1.0 and f["agree_regex_bm25"] == 0.0
    assert f["n_choices"] == 1.0 and f["multi_turn"] == 1.0 and f["margin_bm25"] == 1.0
    rows = [{"conf_bm25": c / 10} for c in range(10)] * 3
    m = fit_deferral(rows, [1 if r["conf_bm25"] > 0.45 else 0 for r in rows], l2=0.01)
    assert m({"conf_bm25": 0.9}) > m({"conf_bm25": 0.1})


def test_build_routers_hybrid_members_and_default_fusion(settings):
    s = settings.model_copy(
        update={
            "strategies": StrategiesConfig.model_validate(
                {
                    "regex": {},
                    "bm25": {"variant": "l"},
                    "embedding": {"provider": "ollama", "model": "e"},
                    "hybrid": {"members": ["regex", "bm25", "embedding"]},
                    "classifier": {},
                }
            )
        }
    )
    routers = build_routers(s, {"hybrid", "classifier"})
    assert set(routers) == {"hybrid", "classifier"}
    h = routers["hybrid"]
    assert h.fusion == "convex" and list(h.members) == ["regex", "bm25", "embedding"]


# ------------------------------------------------------------------ classifier


async def test_tfidf_classifier_routes_and_is_deterministic(skill_options):
    r = ClassifierRouter()
    d = await r.route(skill_input("segunda via do boleto vencido"), skill_options)
    assert d.choice == "pagamentos_reembolsos"
    assert 0 < d.confidence <= 1 and len(d.candidates) == len(skill_options)
    again = await ClassifierRouter().route(
        skill_input("segunda via do boleto vencido"), skill_options
    )
    assert again.candidates == d.candidates


async def test_probe_classifier_uses_frozen_vectors(skill_options):
    emb = EmbeddingRouter(FakeEmbedder())
    r = ClassifierRouter(model="probe", embedding=emb)
    d = await r.route(skill_input("quero devolver o produto"), skill_options)
    assert d.choice == "trocas_devolucoes"
    with pytest.raises(ValueError):
        ClassifierRouter(model="probe")


def test_classifier_training_set_has_no_dataset_text(skill_options):
    texts, labels = ClassifierRouter().training_set(skill_options)
    catalog = {t for o in skill_options for t in option_utterances(o, shots=True, quotes=True)}
    assert set(texts) <= catalog and set(labels) == {o.id for o in skill_options}
