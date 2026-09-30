from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "dataset"))
from common import ALL_TOOLS, CATEGORIES, TARGET_DIST, Case, customer_orders  # noqa: E402

DATA = ROOT / "data"


def _load(name: str) -> list[Case]:
    path = DATA / name
    if not path.exists():
        pytest.skip(f"{name} not generated")
    return [Case.model_validate_json(x) for x in path.read_text().splitlines() if x.strip()]


@pytest.fixture(scope="module")
def dev() -> list[Case]:
    return _load("dataset_dev.jsonl")


@pytest.fixture(scope="module")
def test_() -> list[Case]:
    return _load("dataset_test.jsonl")


@pytest.fixture(scope="module")
def total(dev: list[Case], test_: list[Case]) -> list[Case]:
    return dev + test_


def test_schema_valid_and_seed_present() -> None:
    assert len(_load("seed.jsonl")) >= 100


def test_unique_ids(total: list[Case]) -> None:
    ids = [c.id for c in total]
    assert len(ids) == len(set(ids))


def test_no_overlap(dev: list[Case], test_: list[Case]) -> None:
    assert not {c.id for c in dev} & {c.id for c in test_}
    dev_txt = {tuple(t.content for t in c.turns) for c in dev}
    assert not any(tuple(t.content for t in c.turns) in dev_txt for c in test_)


def test_size_and_split_ratio(total: list[Case], dev: list[Case]) -> None:
    assert 450 <= len(total) <= 550
    assert abs(len(dev) / len(total) - 0.30) <= 0.01


@pytest.mark.parametrize("which", ["total", "dev", "test_"])
def test_distribution_tolerance(which: str, request: pytest.FixtureRequest) -> None:
    cases: list[Case] = request.getfixturevalue(which)
    cnt = Counter(c.category for c in cases)
    for cat in CATEGORIES:
        assert abs(100 * cnt[cat] / len(cases) - 100 * TARGET_DIST[cat]) <= 2.0, (which, cat)


def test_every_tool_at_least_5(total: list[Case]) -> None:
    cnt = Counter(t for c in total for t in c.expected.acceptable_tools)
    low = {t: cnt[t] for t in ALL_TOOLS if cnt[t] < 5}
    assert not low


def test_order_ids_belong_to_customer(total: list[Case]) -> None:
    import json
    import re

    for c in total:
        k = int(c.customer_id[1:])
        mentioned = set(re.findall(r"O\d{4}", json.dumps(c.model_dump(), ensure_ascii=False)))
        assert mentioned <= set(customer_orders(k)), c.id


def test_multiturno_and_abstain_shape(total: list[Case]) -> None:
    for c in total:
        if c.category == "multiturno":
            assert len(c.turns) >= 3
        if c.category == "fora_escopo":
            assert (
                "__abstain__" in c.expected.acceptable_skills
                or "escalate_to_human" in c.expected.acceptable_tools
            )
