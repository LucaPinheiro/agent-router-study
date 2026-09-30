"""scripts/analysis/tune_router.py helpers: folds, overrides (no catalog, no routing)."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "analysis"))

import tune_router  # noqa: E402

from routing_study.settings import Settings  # noqa: E402


def test_tuner_reads_only_the_dev_split():
    assert tune_router.DEV.name == "dataset_dev.jsonl"


def test_folds_are_stratified_and_deterministic():
    rows = [{"id": f"{c}-{i}", "category": c} for c in ("a", "b") for i in range(10)]
    folds = tune_router.folds_of(rows, 5, seed=0)
    assert folds == tune_router.folds_of(rows, 5, seed=0)
    for cat in ("a", "b"):
        assert Counter(f for cid, f in folds.items() if cid.startswith(cat)) == dict.fromkeys(
            range(5), 2
        )


def test_parse_assign_yaml_values():
    assert tune_router.parse_assign("strategies.bm25.k1=0.5,1.2") == (
        ["strategies", "bm25", "k1"],
        [0.5, 1.2],
    )
    assert tune_router.parse_assign("a.b=[1, 2]") == (["a", "b"], [[1, 2]])
    with pytest.raises(SystemExit):
        tune_router.parse_assign("novalue")


def test_patched_overrides_validate():
    base = Settings(_env_file=None, strategies={"bm25": {}})
    s = tune_router.patched(
        base,
        [(["strategies", "bm25", "variant"], "l"), (["strategies", "bm25", "k1"], 0.9)],
    )
    assert s.strategies.bm25.variant == "l" and s.strategies.bm25.k1 == 0.9
    assert base.strategies.bm25.variant == "okapi"
    with pytest.raises(SystemExit):
        tune_router.patched(base, [(["executor", "model"], "x")])


def test_subset_is_stratified_seeded_and_sized():
    rows = [
        {"id": f"{c}-{i}", "category": c}
        for c, n in (("a", 30), ("b", 20), ("c", 10))
        for i in range(n)
    ]
    sub = tune_router.subset_of(rows, 12, seed=0)
    assert len(sub) == 12 and sub == tune_router.subset_of(rows, 12, seed=0)
    assert Counter(r["category"] for r in sub) == {"a": 6, "b": 4, "c": 2}
    assert tune_router.subset_of(rows, 100, seed=0) == rows


def _decision(**usage):
    from routing_study.routers.base import RouteDecision

    return RouteDecision(
        choice="x", confidence=0.9, strategy="llm", cost_usd=0.002, latency_ms=100.0, usage=usage
    )


def test_call_usage_splits_prompt_tokens_by_rendered_characters():
    u = tune_router.call_usage(
        [
            _decision(
                prompt_tokens=1000,
                completion_tokens=30,
                cache_read=800,
                static_chars=900,
                dynamic_chars=100,
            )
        ]
    )
    assert u["static"] == pytest.approx(900) and u["dynamic"] == pytest.approx(100)
    assert u["cost"] == 0.002 and u["ms"] == 100 and u["cache_read"] == 800
    assert not u["parse_fail"]
    assert tune_router.call_usage([_decision(parse_fail=True)])["parse_fail"]


def test_point_metrics_and_selection_tie_break():
    def rec(ok: bool, cost: float, ms: float) -> dict:
        u = dict.fromkeys(("prompt", "completion", "cache_read", "cache_write"), 10.0)
        u |= {"static": 8.0, "dynamic": 2.0, "cost": cost, "ms": ms, "parse_fail": False}
        return {
            "skill_correct": 1.0,
            "tool_correct": float(ok),
            "joint_correct": float(ok),
            "skill_conf": 0.9,
            "tool_conf": 0.9,
            "skill_u": u,
            "tool_u": u,
        }

    recs = {f"c{i}": rec(i % 2 == 0, 0.001, 100.0 * (i + 1)) for i in range(4)}
    fold = {f"c{i}": i % 2 for i in range(4)}
    m = tune_router.point_metrics(recs, fold, 2)
    assert m["joint_correct_mean"] == 0.5 and m["joint_correct_std"] == 0.5
    assert m["cost_per_1k"] == 2.0 and m["prompt_tokens"] == 10.0
    assert m["p50_ms"] == 500.0 and m["p95_ms"] == 800.0
    cheap = dict(m, cost_per_1k=1.0)
    assert tune_router.selection_key(cheap) > tune_router.selection_key(m)


# ---------------------------------------------------------------- F2: failures are errors


class _Pipe:
    """A pipeline stub: returns scripted PipelineResults in order (last one repeats)."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    async def run(self, inp, options):
        self.calls += 1
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def _result(choice, *, strategy="llm", error=None, parse_fail=False):
    from routing_study.routers.base import RouteDecision
    from routing_study.routers.pipeline import PipelineResult

    usage = {"error": error} if error else {"parse_fail": True} if parse_fail else {}
    d = RouteDecision(choice=choice, confidence=0.9 if choice else 0.0, strategy=strategy)
    d.usage = usage
    return PipelineResult(
        decision=d,
        resolved_by=strategy if choice else None,
        abstained=choice is None,
        mode="single",
        steps=[d],
        routing_error=f"{strategy}: {error}" if error and not choice else None,
    )


class _Catalog:
    def skill_options(self):
        return []

    def tool_options(self, skill):
        return []


OOS_CASE = {
    "id": "oos",
    "category": "fora_escopo",
    "turns": [{"role": "user", "content": "qual a capital da franca?"}],
    "expected": {"acceptable_skills": ["__abstain__"], "acceptable_tools": ["__abstain__"]},
}


@pytest.mark.parametrize("kw", [{"error": "Timeout"}, {"parse_fail": True}])
async def test_f2_failed_stage_is_an_error_scored_wrong_never_an_abstention(monkeypatch, kw):
    """An out-of-scope gold would score a failed (choice None) skill stage as a CORRECT
    abstention; under ITT it is an error and counts as wrong."""
    monkeypatch.setattr(tune_router, "ERROR_RETRIES", 0)
    pipe = _Pipe([_result(None, **kw)])
    monkeypatch.setattr(tune_router, "build_routers", lambda s, w: {})
    monkeypatch.setattr(tune_router, "build_pipeline", lambda s, lv, r: pipe)
    base = Settings(_env_file=None)
    recs = await tune_router.evaluate(base, [OOS_CASE], _Catalog())
    rec = recs["oos"]
    assert rec["error"] and rec["joint_correct"] == rec["skill_correct"] == 0.0
    assert rec["abstain_correct"] == 0.0


async def test_f2_infra_error_is_retried_and_a_recovery_is_scored(monkeypatch):
    monkeypatch.setattr(tune_router.asyncio, "sleep", _nosleep)
    skill = _Pipe([_result(None, error="Throttling"), _result("__global__")])
    tool = _Pipe([_result("escalate_to_human")])
    pipes = iter([skill, tool])
    monkeypatch.setattr(tune_router, "build_routers", lambda s, w: {})
    monkeypatch.setattr(tune_router, "build_pipeline", lambda s, lv, r: next(pipes))
    recs = await tune_router.evaluate(Settings(_env_file=None), [OOS_CASE], _Catalog())
    assert skill.calls == 2 and recs["oos"]["error"] is None
    assert recs["oos"]["joint_correct"] == 1.0


async def _nosleep(_s):
    return None


def test_f2_point_metrics_count_errors_and_selection_penalizes_them():
    def rec(ok: bool, error: str | None = None) -> dict:
        u = dict.fromkeys(("prompt", "completion", "cache_read", "cache_write"), 0.0)
        u |= {"static": 0.0, "dynamic": 0.0, "cost": 0.0, "ms": 1.0, "parse_fail": False}
        u["error"] = bool(error)
        return {
            "skill_correct": float(ok),
            "tool_correct": float(ok),
            "joint_correct": float(ok),
            "skill_conf": None,
            "tool_conf": None,
            "skill_u": u,
            "tool_u": u,
            "error": error,
        }

    fold = {f"c{i}": 0 for i in range(4)}
    clean = tune_router.point_metrics({f"c{i}": rec(i < 2) for i in range(4)}, fold, 1)
    failing = tune_router.point_metrics(
        {f"c{i}": rec(i < 2, None if i < 3 else "llm: Timeout") for i in range(4)}, fold, 1
    )
    assert failing["errors"] == 1 and failing["error_rate"] == 0.25
    assert failing["joint_correct_mean"] == 0.5  # the error row counts as wrong (ITT)
    assert tune_router.selection_key(clean) > tune_router.selection_key(failing)
