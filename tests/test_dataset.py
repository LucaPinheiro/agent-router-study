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


def _generate():  # noqa: ANN202
    import generate

    return generate


def test_a3_generator_asks_only_for_real_parameter_names() -> None:
    gen = _generate()
    prompt = gen.build_prompt("direto", "update_delivery_address", 1, [("C001", ["O0001"])])
    assert "address, query" not in prompt
    assert "update_delivery_address" in gen.TOOL_PARAMS
    assert {"street", "number", "postal_code"} <= set(gen.TOOL_PARAMS["update_delivery_address"])
    assert "street" in prompt and "postal_code" in prompt
    slot = ("C001", ["O0001", "O0002", "O0003"])
    item = {
        "turns": [{"role": "user", "content": "muda o endereço do O0001"}],
        "acceptable_tools": ["update_delivery_address"],
        "args": {"order_id": "O0001", "address": "Rua A, 1"},
    }
    assert gen.to_case("direto", "update_delivery_address", item, slot, "x") is None
    item["args"] = {"order_id": "O0001", "street": "Rua A", "number": "1"}
    assert gen.to_case("direto", "update_delivery_address", item, slot, "x") is not None


def test_a8_split_reproduces_dev_and_test_including_label_fixes(tmp_path: Path) -> None:
    import json
    import shutil

    import split

    for name in ("seed.jsonl", "synthetic.jsonl"):
        shutil.copy(DATA / name, tmp_path / name)
    split.main(data=tmp_path, out=tmp_path)
    for name in ("dataset_dev.jsonl", "dataset_test.jsonl"):
        built = [json.loads(x) for x in (tmp_path / name).read_text().splitlines()]
        current = [json.loads(x) for x in (DATA / name).read_text().splitlines()]
        assert [(r["id"], r["expected"], r.get("label_fix")) for r in built] == [
            (r["id"], r["expected"], r.get("label_fix")) for r in current
        ], name
        assert (tmp_path / name).read_bytes() == (DATA / name).read_bytes(), name
    fixed = [x for x in (tmp_path / "synthetic.jsonl").read_text().splitlines() if "label_fix" in x]
    assert len(fixed) == 15


def test_a8_split_refuses_to_drop_a_label_fix(tmp_path: Path) -> None:
    import split

    cases = split.load(DATA / "seed.jsonl") + split.load(DATA / "synthetic.jsonl")
    assert sum(c.label_fix is not None for c in cases) == 15
    broken = [c.model_copy(update={"label_fix": None}) if c.label_fix else c for c in cases]
    with pytest.raises(AssertionError, match="label_fix"):
        split.check_label_fixes(cases, *split.build(broken))


def test_a9_env_var_wins_over_a_blank_dotenv_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gen = _generate()
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-env")
    assert gen.load_env(env) == "sk-env"
    env.write_text("OPENROUTER_API_KEY='sk-file'\n")
    assert gen.load_env(env) == "sk-env"
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert gen.load_env(env) == "sk-file"
    env.write_text("OPENROUTER_API_KEY=\n")
    with pytest.raises(SystemExit):
        gen.load_env(env)
    with pytest.raises(SystemExit):
        gen.load_env(tmp_path / "missing.env")


@pytest.mark.parametrize("status", [401, 402])
def test_a9_auth_and_credit_errors_fail_fast(status: int) -> None:
    import httpx

    gen = _generate()
    hits: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(1)
        return httpx.Response(status, json={"error": {"message": "no"}})

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(SystemExit, match=str(status)),
    ):
        gen.call(client, "k", "m", "p")
    assert len(hits) == 1


def test_a9_never_overwrites_with_fewer_rows_without_force(tmp_path: Path) -> None:
    gen = _generate()
    out = tmp_path / "synthetic.jsonl"
    out.write_text('{"id": "a"}\n{"id": "b"}\n')
    with pytest.raises(SystemExit, match="--force"):
        gen.write_cases(out, [], force=False)
    assert out.read_text() == '{"id": "a"}\n{"id": "b"}\n'
    gen.write_cases(out, [], force=True)
    assert out.read_text() == ""


# ---------------------------------------------------------------- test-v2 (confirmatory split)

V2_QUOTA = {
    "direto": 105,
    "parafrase": 87,
    "ambiguo": 70,
    "multiturno": 35,
    "fora_escopo": 35,
    "adversarial": 17,
}
AUDIT_DIR = DATA / "audit"


@pytest.fixture(scope="module")
def v2() -> list[Case]:
    return _load("dataset_test_v2.jsonl")


def _module(name: str):  # noqa: ANN202
    import importlib

    return importlib.import_module(name)


def test_v2_schema_source_and_ids(v2: list[Case], total: list[Case]) -> None:
    ids = [c.id for c in v2]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("v2-") for i in ids)
    assert not set(ids) & {c.id for c in total}
    assert {c.source for c in v2} == {"synthetic_v2"}
    for c in v2:  # only a human decision may mark a case reviewed
        assert c.reviewed == bool((c.label_audit or {}).get("human_decision")), c.id


def test_v2_category_quotas_match_test_v1(v2: list[Case], test_: list[Case]) -> None:
    cnt = Counter(c.category for c in v2)
    assert dict(Counter(c.category for c in test_)) == V2_QUOTA
    if len(v2) == sum(V2_QUOTA.values()):  # exact until a human drops a case
        assert dict(cnt) == V2_QUOTA
    for cat in CATEGORIES:
        assert abs(100 * cnt[cat] / len(v2) - 100 * TARGET_DIST[cat]) <= 2.0, cat


def test_v2_per_tool_balance(v2: list[Case]) -> None:
    any_ = Counter(t for c in v2 for t in c.expected.acceptable_tools)
    first = Counter(c.expected.acceptable_tools[0] for c in v2)
    assert min(any_[t] for t in ALL_TOOLS) >= 8, any_
    assert min(first[t] for t in ALL_TOOLS) >= 8, first


def test_v2_order_ids_belong_to_customer(v2: list[Case]) -> None:
    import json
    import re

    for c in v2:
        k = int(c.customer_id[1:])
        mentioned = set(re.findall(r"O\d{4}", json.dumps(c.model_dump(), ensure_ascii=False)))
        assert mentioned <= set(customer_orders(k)), c.id


def test_v2_args_use_real_parameter_names(v2: list[Case]) -> None:
    params = _generate().TOOL_PARAMS
    for c in v2:
        allowed = {p for t in c.expected.acceptable_tools for p in params.get(t, [])}
        assert set(c.expected.args) <= allowed, c.id


def test_v2_label_policy_shapes(v2: list[Case]) -> None:
    for c in v2:
        tools = c.expected.acceptable_tools
        if c.category == "fora_escopo":
            assert "__abstain__" in tools, c.id
        if c.category == "multiturno":
            assert len(c.turns) >= 3, c.id
        if c.category == "ambiguo" and (c.label_audit or {}).get("decision") != "fixed":
            assert len(tools) >= 2, c.id  # an agreed audit fix may narrow it
        if c.category in ("direto", "parafrase", "multiturno"):
            assert "__abstain__" not in tools, c.id


def test_v2_no_lexical_overlap_with_existing_cases_or_catalog(v2: list[Case]) -> None:
    overlap = _module("overlap")
    existing = _load("seed.jsonl") + _load("synthetic.jsonl")
    refs = [overlap.case_text(c) for c in existing]
    units = overlap.catalog_units()
    assert len(units) > 300
    hits = {c.id: h for c in v2 if (h := overlap.lexical_hit(c, refs, units))}
    assert not hits


def test_v2_semantic_overlap_report_is_clean() -> None:
    import json

    path = AUDIT_DIR / "overlap_report.json"
    if not path.exists():
        pytest.skip("overlap report not generated (needs the local embedder)")
    rep = json.loads(path.read_text())["test_v2"]
    assert rep["semantic_vs_500_cases"]["n_ge_0.9"] == 0
    assert rep["semantic_vs_catalog"]["n_ge_0.9"] == 0
    assert rep["lexical_vs_500_cases"]["n_ge_0.9"] == 0
    assert rep["lexical_vs_catalog"]["n_ge_0.9"] == 0
    assert rep["id_overlap_with_500"] == 0


def test_v2_audit_outcome_recorded_on_every_row(v2: list[Case]) -> None:
    for c in v2:
        audit = c.label_audit or {}
        assert audit.get("decision") in ("keep", "fixed", "flagged"), c.id
        if audit["decision"] == "fixed":
            assert audit.get("original"), c.id
    assert "label_audit" not in (DATA / "dataset_test.jsonl").read_text()  # test-v1 untouched


def test_v2_frozen_sha256_matches_dataset_card() -> None:
    import hashlib
    import re

    card = (ROOT / "docs" / "dataset-card.md").read_text()
    m = re.search(r"`data/dataset_test_v2\.jsonl`\s*\|\s*`([0-9a-f]{64})`", card)
    assert m, "freeze table missing in docs/dataset-card.md"
    sha = hashlib.sha256((DATA / "dataset_test_v2.jsonl").read_bytes()).hexdigest()
    assert sha == m.group(1), "test-v2 changed after the freeze: re-freeze docs/dataset-card.md"


def _verdict(ok: bool, tools: list[str], args_ok: bool = True, args=None) -> dict:  # noqa: ANN001
    return {
        "gold_acceptable": ok,
        "proposed_tools": tools,
        "args_correct": args_ok,
        "proposed_args": args or [],
        "missing_alternatives": [],
    }


def test_audit_adjudication_rule() -> None:
    audit = _module("audit")
    case = Case.model_validate(
        {
            "id": "x",
            "category": "direto",
            "customer_id": "C001",
            "source": "synthetic_v2",
            "turns": [{"role": "user", "content": "cadê meu pedido O0001?"}],
            "expected": {
                "acceptable_skills": ["pedidos_logistica"],
                "acceptable_tools": ["get_order_status"],
                "args": {"order_id": "O0001"},
            },
        }
    )
    keep = audit.adjudicate_case(case, _verdict(True, ["x"]), _verdict(True, ["y"]))
    assert keep["decision"] == "keep" and keep["fixed_expected"] is None
    fix = ["track_shipment", "get_order_status"]
    same = audit.adjudicate_case(
        case, _verdict(False, fix), _verdict(False, ["track_shipment", "get_order_status"])
    )
    assert same["decision"] == "fixed"
    assert same["fixed_expected"]["acceptable_tools"] == fix
    assert same["fixed_expected"]["args"] == {"order_id": "O0001"}
    other_first = audit.adjudicate_case(case, _verdict(False, fix), _verdict(False, fix[::-1]))
    assert other_first["decision"] == "flagged"
    split = audit.adjudicate_case(case, _verdict(True, ["x"]), _verdict(False, fix))
    assert split["decision"] == "flagged"
    bad_args = [{"name": "order_id", "value": "O0002"}]
    args_fix = audit.adjudicate_case(
        case,
        _verdict(True, ["x"], False, bad_args),
        _verdict(True, ["y"], False, [{"name": "order_id", "value": " o0002 "}]),
    )
    assert args_fix["decision"] == "fixed"
    assert args_fix["fixed_expected"]["args"] == {"order_id": "O0002"}
    args_split = audit.adjudicate_case(
        case, _verdict(True, ["x"], False, bad_args), _verdict(True, ["y"])
    )
    assert args_split["decision"] == "flagged"
    invalid = [{"name": "street", "value": "Rua A"}]
    inv = audit.adjudicate_case(
        case, _verdict(True, ["x"], False, invalid), _verdict(True, ["y"], False, invalid)
    )
    assert inv["decision"] == "flagged" and "fix_invalid" in inv["reasons"]


def test_cohen_kappa_and_wilson() -> None:
    audit = _module("audit")
    assert audit.cohen_kappa([1, 1, 0, 0], [1, 0, 0, 0]) == 0.5
    assert audit.cohen_kappa(["a", "b"], ["a", "b"]) == 1.0
    assert audit.cohen_kappa([1, 1], [1, 1]) is None  # chance agreement 1: undefined
    lo, hi = audit.wilson(80, 100)
    assert 0.70 < lo < 0.72 and 0.86 < hi < 0.87


def test_review_page_is_self_contained() -> None:
    page = AUDIT_DIR / "review.html"
    if not page.exists():
        pytest.skip("review page not built")
    text = page.read_text()
    assert "<link" not in text and "@import" not in text
    assert 'src="http' not in text and "src='http" not in text
    assert "label-decisions/v1" in text and "Export decisions JSON" in text
