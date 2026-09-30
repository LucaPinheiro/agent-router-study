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
