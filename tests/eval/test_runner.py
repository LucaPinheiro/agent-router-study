"""Runner bookkeeping: results files, thread ids, case sampling, run metadata (no network)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from routing_study.eval import runner as runner_mod
from routing_study.eval.runner import Runner
from routing_study.settings import Settings


def _runner(name: str = "same-name", **kw: object) -> Runner:
    return Runner(
        Settings(_env_file=None, experiment_id="x"), split="dev", mode="e2e", run_name=name, **kw
    )  # type: ignore[arg-type]


def test_a10_thread_id_is_unique_per_invocation() -> None:
    a, b = _runner(), _runner()
    assert a.thread_id("case-1", 1) != b.thread_id("case-1", 1)
    assert a.thread_id("case-1", 1) == a.thread_id("case-1", 1)
    assert a.thread_id("case-1", 1).startswith("same-name:")
    assert a.thread_id("case-1", 1) != a.thread_id("case-1", 2)


def test_a10_existing_results_file_is_not_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner_mod, "RESULTS_DIR", tmp_path)
    old = tmp_path / "same-name.jsonl"
    old.write_text('{"old": 1}\n')
    with pytest.raises(FileExistsError, match="--overwrite"):
        asyncio.run(_runner().run([]))
    assert old.read_text() == '{"old": 1}\n'
    # checked before any network/redis work; --overwrite gets past it
    with pytest.raises(ValueError, match="REDIS_URL"):
        asyncio.run(_runner(overwrite=True).run([]))


def _dataset(tmp_path: Path, sizes: dict[str, int]) -> Path:
    import json

    rows = [
        {
            "id": f"{c}{i:02d}",
            "category": c,
            "customer_id": "C001",
            "turns": [{"role": "user", "content": "x"}],
            "expected": {"acceptable_skills": ["__global__"], "acceptable_tools": ["x"]},
        }
        for c, n in sizes.items()
        for i in range(n)
    ]
    (tmp_path / "dataset_dev.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    return tmp_path


def test_a11_limit_is_a_stratified_seeded_sample(tmp_path: Path) -> None:
    from collections import Counter

    from routing_study.eval.runner import load_cases

    data = _dataset(tmp_path, {"direto": 30, "ambiguo": 20, "fora_escopo": 10})
    sample = load_cases("dev", 12, data_dir=data)
    assert len(sample) == 12
    assert Counter(c.category for c in sample) == {"direto": 6, "ambiguo": 4, "fora_escopo": 2}
    # not the head of each category, but the same sample every time (fixed seed)
    assert [c.id for c in sample] == [c.id for c in load_cases("dev", 12, data_dir=data)]
    assert {c.id for c in sample} != {
        "direto00",
        "direto01",
        "direto02",
        "direto03",
        "direto04",
        "direto05",
        "ambiguo00",
        "ambiguo01",
        "ambiguo02",
        "ambiguo03",
        "fora_escopo00",
        "fora_escopo01",
    }
    assert len(load_cases("dev", 1000, data_dir=data)) == 60


def test_a11_limit_must_be_positive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from routing_study.cli import app
    from routing_study.eval.runner import load_cases

    data = _dataset(tmp_path, {"direto": 3})
    with pytest.raises(ValueError, match="limit"):
        load_cases("dev", 0, data_dir=data)
    monkeypatch.setattr("routing_study.cli.load_dotenv", lambda *a, **k: False)
    res = CliRunner().invoke(
        app, ["run", "--config", "config/experiments/e9_regex_jev_llm.yaml", "--limit", "0"]
    )
    assert res.exit_code == 2


def test_a12_config_hash_covers_regex_rules_content(tmp_path: Path) -> None:
    from routing_study.eval.runner import config_hash
    from routing_study.settings import RegexStrategy, StrategiesConfig

    rules = tmp_path / "rules.yaml"
    rules.write_text("skills: []\n")
    settings = Settings(
        _env_file=None,
        experiment_id="x",
        strategies=StrategiesConfig(regex=RegexStrategy(rules_path=str(rules))),
    )
    before = config_hash(settings)
    assert config_hash(settings) == before
    rules.write_text("skills: [{id: pedidos_logistica}]\n")
    assert config_hash(settings) != before


def test_a12_prompt_hash_covers_router_prompt_load_skill_and_system_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from routing_study import prompts
    from routing_study.eval.runner import run_prompt_hash
    from routing_study.graph import nodes
    from routing_study.routers import llm

    base = run_prompt_hash()
    assert run_prompt_hash() == base
    for target, name, value in (
        (llm, "templates", lambda lang, t=llm.templates: {**t(lang), "role": "Route: {noun}."}),
        (nodes, "ESCALATION_TEXT", "outro texto"),
        (prompts, "HOST_RULES", "regras novas"),
        (nodes, "load_skill_tool", lambda catalog: {"name": "load_skill", "v": 2}),
    ):
        with monkeypatch.context() as m:
            m.setattr(target, name, value)
            assert run_prompt_hash() != base, name
    assert run_prompt_hash() == base


def test_a12_git_sha_flags_a_dirty_tree(tmp_path: Path) -> None:
    import subprocess

    from routing_study.eval.runner import git_sha

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "a.txt").write_text("1")
    git("add", "a.txt")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    clean = git_sha(tmp_path)
    assert clean and "dirty" not in clean
    (tmp_path / "a.txt").write_text("2")
    dirty = git_sha(tmp_path)
    assert dirty.startswith(clean + "-dirty.")
    (tmp_path / "a.txt").write_text("3")
    assert git_sha(tmp_path) != dirty  # the diff hash tells two dirty trees apart
    (tmp_path / "b.txt").write_text("new")  # untracked files count too
    assert git_sha(tmp_path) not in (clean, dirty)


def test_a15_make_targets_select_the_right_tests() -> None:
    import shutil
    import subprocess

    if shutil.which("make") is None:
        pytest.skip("make not installed")

    def recipe(target: str) -> str:
        return subprocess.run(
            ["make", "-n", target], capture_output=True, text=True, check=True
        ).stdout

    # tests/integration/conftest.py skips integration tests unless `-m integration` is given
    assert "-m integration" in recipe("e2e")
    assert "tests/integration" in recipe("e2e")
    assert "not integration" in recipe("test")
    assert "ruff format --check" in recipe("lint")


# ---------------------------------------------------------------- review M2 / M3


def test_m3_results_are_written_to_partial_then_renamed(tmp_path: Path) -> None:
    from routing_study.eval.runner import results_writer

    out = tmp_path / "run.jsonl"
    with results_writer(out, overwrite=False) as fh:
        fh.write("row\n")
        assert (tmp_path / "run.jsonl.partial").exists() and not out.exists()
    assert out.read_text() == "row\n" and not (tmp_path / "run.jsonl.partial").exists()
    # a crash leaves only the .partial: never mistaken for a finished run
    crashed = tmp_path / "crash.jsonl"
    with pytest.raises(RuntimeError), results_writer(crashed, overwrite=False) as fh:
        fh.write("half\n")
        raise RuntimeError("boom")
    assert not crashed.exists() and (tmp_path / "crash.jsonl.partial").exists()
    # a leftover .partial (crashed or concurrent run) blocks a new run unless --overwrite
    with pytest.raises(FileExistsError), results_writer(crashed, overwrite=False):
        pass
    with results_writer(crashed, overwrite=True) as fh:
        fh.write("full\n")
    assert crashed.read_text() == "full\n"


def test_m2_rows_carry_code_dataset_and_scorer_provenance(tmp_path: Path) -> None:
    from routing_study.eval.scorers import scorer_hash

    r = _runner()
    r.meta = {
        "git_sha": "abc1234",
        "config_hash": "c",
        "catalog_hash": "k",
        "prompt_hash": "p",
        "dataset_sha256": "d" * 64,
        "scorer_hash": scorer_hash(),
    }
    case = runner_mod.Case("c1", "direto", "C001", [], {"acceptable_skills": []})
    base = r.base_record(case, 2)
    for k in ("git_sha", "dataset_sha256", "scorer_hash", "config_hash"):
        assert base[k] == r.meta[k]
    assert base["rep"] == 2 and base["case_id"] == "c1"


def test_m2_cost_tally_records_the_served_executor_model_and_provider() -> None:
    from langchain_core.outputs import LLMResult

    from routing_study.tracing.cost import CostTally

    t = CostTally()
    t.on_llm_end(
        LLMResult(
            generations=[],
            llm_output={
                "token_usage": {"cost": 0.01, "prompt_tokens": 5},
                "model_name": "anthropic/claude-sonnet-5",
                "provider": "Anthropic",
            },
        )
    )
    assert t.served_models == ["anthropic/claude-sonnet-5"] and t.providers == ["Anthropic"]


def test_dataset_sha256_is_na_for_in_memory_splits(tmp_path) -> None:
    from routing_study.eval.runner import dataset_sha256

    assert dataset_sha256("integration", tmp_path) == "n/a"
    (tmp_path / "dataset_dev.jsonl").write_text("{}\n")
    assert len(dataset_sha256("dev", tmp_path)) == 64
