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
