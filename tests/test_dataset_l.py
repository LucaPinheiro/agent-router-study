"""Phase-2 large-catalog splits (dev-L now, test-L after the T5 freeze): schema, quotas, gold
tools in the 62-tool catalog, eval-loader compatibility, lexical catalog leakage against the
LARGE catalog units (the repo rule of tests/test_leakage.py) and the frozen sha."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "scripts" / "dataset"))
from common_l import ORIG_TOOLS, CaseL  # noqa: E402

SPLITS = {
    "dev_l": {
        "direto": 45,
        "parafrase": 37,
        "ambiguo": 30,
        "multiturno": 15,
        "fora_escopo": 15,
        "adversarial": 8,
    },
    "test_l": {
        "direto": 90,
        "parafrase": 75,
        "ambiguo": 60,
        "multiturno": 30,
        "fora_escopo": 30,
        "adversarial": 15,
    },
}
LARGE_TOOLS = {
    t["name"]
    for t in json.loads((ROOT / "mcp_server" / "tools_list_large.json").read_text())["tools"]
}


def _load(split: str) -> list[CaseL]:
    path = DATA / f"dataset_{split}.jsonl"
    if not path.exists():
        pytest.skip(f"{path.name} not generated")
    return [CaseL.model_validate_json(x) for x in path.read_text().splitlines() if x.strip()]


@pytest.mark.parametrize("split", list(SPLITS))
def test_schema_quotas_and_ids(split: str) -> None:
    cases = _load(split)
    assert Counter(c.category for c in cases) == Counter(SPLITS[split])
    assert len({c.id for c in cases}) == len(cases)
    assert all(c.source == "synthetic_l" for c in cases)


@pytest.mark.parametrize("split", list(SPLITS))
def test_gold_tools_exist_in_large_catalog(split: str) -> None:
    for c in _load(split):
        assert set(c.expected.acceptable_tools) <= LARGE_TOOLS | {"__abstain__"}, c.id
        orig = (c.label_audit or {}).get("original")
        if orig:
            assert set(orig["acceptable_tools"]) <= LARGE_TOOLS | {"__abstain__"}, c.id


@pytest.mark.parametrize("split", list(SPLITS))
def test_single_label_coverage_and_orig_share(split: str) -> None:
    cases = _load(split)
    single = [
        (c.label_audit or {}).get("original", {}).get("acceptable_tools")
        or c.expected.acceptable_tools
        for c in cases
        if c.category in ("direto", "parafrase", "multiturno")
    ]
    assert {t[0] for t in single} == LARGE_TOOLS  # every tool targeted at least once
    assert sum(t[0] in ORIG_TOOLS for t in single) / len(single) >= 0.30


@pytest.mark.parametrize("split", list(SPLITS))
def test_eval_loader_reads_split(split: str) -> None:
    from routing_study.eval.runner import load_cases

    rows = _load(split)
    loaded = load_cases(split)
    assert sorted(c.id for c in loaded) == sorted(c.id for c in rows)
    assert all(c.expected["acceptable_tools"] for c in loaded)


@pytest.mark.parametrize("split", list(SPLITS))
def test_no_large_catalog_text_lexically_matches_a_user_turn(split: str) -> None:
    import overlap

    units = overlap.leak_units_large()
    leaks = [(c.id, hit) for c in _load(split) if (hit := overlap.leak_hit_units(c, units))]
    assert not leaks, leaks


@pytest.mark.parametrize("split", list(SPLITS))
def test_frozen_sha256_matches_dataset_card(split: str) -> None:
    path = DATA / f"dataset_{split}.jsonl"
    if not path.exists():
        pytest.skip(f"{split} not generated")
    card = (ROOT / "docs" / "dataset-card.md").read_text()
    m = re.search(rf"`data/dataset_{split}\.jsonl`\s*\|\s*`([0-9a-f]{{64}})`", card)
    assert m, f"{split} freeze row missing in docs/dataset-card.md"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == m.group(1)


def test_test_l_disjoint_from_dev_l_and_orig_subset() -> None:
    dev, test = _load("dev_l"), _load("test_l")
    assert not {c.id for c in dev} & {c.id for c in test}
    dev_txt = {tuple(t.content for t in c.turns) for c in dev}
    assert not any(tuple(t.content for t in c.turns) in dev_txt for c in test)
    orig = [
        c
        for c in test
        if set(
            (c.label_audit or {}).get("original", {}).get("acceptable_tools")
            or c.expected.acceptable_tools
        )
        <= set(ORIG_TOOLS)
    ]
    assert len(orig) >= 60  # plan §2: the paired catalog-size analysis needs >= 60
