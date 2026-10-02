"""Run manifest (F11): version guard, resume, completion, retry rule, priority order."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from routing_study.eval import manifest as mf
from routing_study.eval.runner import config_hash, existing_rows, results_writer, run_prompt_hash

E1 = Path("config/experiments/e1_regex.yaml")


def _dataset(tmp: Path, n: int = 10) -> Path:
    data = tmp / "data"
    data.mkdir()
    cats = ("direto", "ambiguo")
    rows = [
        {
            "id": f"c{i:02d}",
            "category": cats[i % 2],
            "customer_id": "C001",
            "turns": [{"role": "user", "content": "cadê meu pedido?"}],
            "expected": {
                "acceptable_skills": ["pedidos_logistica"],
                "acceptable_tools": ["get_order_status"],
                "args": {},
            },
        }
        for i in range(n)
    ]
    (data / "dataset_dev.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return data


def _manifest(tmp: Path, **run) -> mf.Manifest:
    entry = {"name": "r1", "config": str(E1), "mode": "routing-only"} | run
    return mf.Manifest(split="dev", results_dir=tmp / "results", runs=[entry])


def _row(case: str, rep: int, error: str | None = None, **kw) -> dict:
    from routing_study.settings import load_settings

    return {
        "run_name": "r1",
        "config": "e1_regex",
        "split": "dev",
        "case_id": case,
        "rep": rep,
        "mode": "routing-only",
        "native": False,
        "error": error,
        "config_hash": kw.get("config_hash", config_hash(load_settings(E1))),
        "prompt_hash": kw.get("prompt_hash", run_prompt_hash()),
        "skill": {"choice": "pedidos_logistica", "resolved_by": "regex", "steps": []},
        "tool": {"choice": "get_order_status", "resolved_by": "regex", "steps": []},
        "calls": [],
        "cost_usd": {"routing": 0.0, "agent": 0.0, "total": 0.0},
        "latency_ms": {"turn": 1.0, "routing": 1.0, "executor": None},
    }


def test_template_manifest_validates_and_is_ordered_by_priority():
    m = mf.load_manifest(Path("config/study_manifest.yaml"))
    assert m.split == "test_v2" and m.error_budget == 0.02 and m.max_infra_retries == 2
    order = [r.priority for r in m.ordered()]
    assert order == sorted(order)
    names = {r.name for r in m.runs}
    for c in m.contrasts:
        assert c.run in names and c.reference in names, c
    # prereg-v1: S1 has no test contrast (tuned == canonical for every LLM-type router)
    assert {c.family for c in m.contrasts} >= {"H", "S2", "S4"}
    for r in m.runs:  # frozen: every config exists and every entry carries its hashes
        assert r.config.exists(), r.config
        assert r.config_hash and r.prompt_hash, r.name


def test_case_filter_is_a_seeded_stratified_subset(tmp_path):
    data = _dataset(tmp_path)
    run = _manifest(tmp_path, cases={"limit": 4}).runs[0]
    a = mf.select_cases(run, "dev", data)
    assert len(a) == 4 and a == mf.select_cases(run, "dev", data)
    assert {c.category for c in a} == {"direto", "ambiguo"}
    ids = tmp_path / "ids.txt"
    ids.write_text("c01\nc03\n")
    run = _manifest(tmp_path, cases={"ids_file": str(ids)}).runs[0]
    assert [c.id for c in mf.select_cases(run, "dev", data)] == ["c01", "c03"]


def test_status_completion_and_error_budget(tmp_path):
    data = _dataset(tmp_path)
    m = _manifest(tmp_path, reps=2)
    cases = mf.select_cases(m.runs[0], "dev", data)
    rows = [_row(c.id, 1) for c in cases]
    st = mf.status(m, m.runs[0], cases, rows)
    assert (st["wanted"], st["present"], st["missing"], st["complete"]) == (20, 10, 10, False)
    rows += [_row(c.id, 2) for c in cases]
    assert mf.status(m, m.runs[0], cases, rows)["complete"]
    rows[0]["error"] = "llm: Timeout"  # 1/20 = 5% > 2%
    st = mf.status(m, m.runs[0], cases, rows)
    assert st["errors"] == 1 and not st["complete"]


def test_resume_appends_and_repairs_a_torn_line_without_deleting(tmp_path):
    out = tmp_path / "run.jsonl"
    partial = tmp_path / "run.jsonl.partial"
    partial.write_text('{"case_id": "a", "rep": 1}\n{"case_id": "b", "re')
    assert [r["case_id"] for r in existing_rows(out)] == ["a"]
    assert list(tmp_path.glob("run.jsonl.partial.torn-*"))  # the torn bytes are kept
    with results_writer(out, overwrite=False, resume=True) as fh:
        fh.write('{"case_id": "b", "rep": 1}\n')
    assert [json.loads(x)["case_id"] for x in out.read_text().splitlines()] == ["a", "b"]
    with results_writer(out, overwrite=False, resume=True) as fh:  # a finished file too
        fh.write('{"case_id": "c", "rep": 1}\n')
    assert len(out.read_text().splitlines()) == 3 and not partial.exists()


def test_quarantine_keeps_error_rows_for_audit(tmp_path):
    res = tmp_path / "results"
    res.mkdir()
    (res / "r1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in [_row("a", 1), _row("b", 1, error="x")]) + "\n"
    )
    dest = mf.quarantine_errors(res, "r1")
    assert dest.name == "r1.retry1.errors.jsonl" and json.loads(dest.read_text())["case_id"] == "b"
    assert [r["case_id"] for r in mf.read_rows(res, "r1")] == ["a"]
    assert mf.retries_used(res, "r1") == 1


def _fake_runner(tmp: Path, fail: dict[int, set[str]]):
    """A run_once that writes the missing keys; pass k fails the case ids in fail[k]."""
    passes = []

    async def run_once(run, settings, split, cases, per_turn):
        passes.append(per_turn)
        k = len(passes)
        out = tmp / "results" / f"{run.name}.jsonl"
        out.parent.mkdir(exist_ok=True)
        done = {(r["case_id"], r["rep"]) for r in mf.read_rows(out.parent, run.name)}
        with out.open("a") as fh:
            for rep in range(1, run.reps + 1):
                for c in cases:
                    if (c.id, rep) not in done:
                        err = "llm: Timeout" if c.id in fail.get(k, set()) else None
                        fh.write(json.dumps(_row(c.id, rep, err)) + "\n")
        return out

    return run_once, passes


def _execute(tmp, m, run_once, **kw):
    return mf.execute(
        m, tmp / "m.yaml", data_dir=tmp / "data", run_once=run_once, echo=lambda _: None, **kw
    )


def test_execute_retries_infra_errors_then_completes(tmp_path, monkeypatch):
    _dataset(tmp_path)
    monkeypatch.setattr(mf, "RESCORED", tmp_path / "rescored")
    m = _manifest(tmp_path)
    run_once, passes = _fake_runner(tmp_path, {1: {"c00", "c01"}})  # 20% errors on pass 1
    assert _execute(tmp_path, m, run_once) == {"r1": "complete"}
    assert len(passes) == 2 and passes[0] == {}  # e1 is free: no paid provider
    assert (tmp_path / "results" / "r1.retry1.errors.jsonl").exists()
    rows = mf.read_rows(tmp_path / "results", "r1")
    assert len(rows) == 10 and not any(r["error"] for r in rows)
    assert (tmp_path / "rescored" / "r1.jsonl").exists()
    log = (tmp_path / "results" / "manifest-m.log").read_text()
    assert "RETRY r1" in log and "COMPLETE r1" in log
    # a complete run is skipped
    assert _execute(tmp_path, m, run_once) == {"r1": "complete"} and len(passes) == 2


def test_execute_flags_a_run_above_budget_after_two_retries(tmp_path, monkeypatch):
    _dataset(tmp_path)
    monkeypatch.setattr(mf, "RESCORED", tmp_path / "rescored")
    always = {k: {"c00"} for k in range(1, 10)}
    run_once, passes = _fake_runner(tmp_path, always)
    assert _execute(tmp_path, _manifest(tmp_path), run_once) == {"r1": "flagged"}
    assert len(passes) == 3  # first pass + 2 retries, never more
    assert "redo this run from scratch" in (tmp_path / "results" / "manifest-m.log").read_text()


def test_execute_refuses_mixed_versions_and_wrong_prompt_track(tmp_path, monkeypatch):
    _dataset(tmp_path)
    monkeypatch.setattr(mf, "RESCORED", tmp_path / "rescored")
    run_once, passes = _fake_runner(tmp_path, {})
    res = tmp_path / "results"
    res.mkdir()
    (res / "r1.jsonl").write_text(json.dumps(_row("c00", 1, config_hash="old")) + "\n")
    assert _execute(tmp_path, _manifest(tmp_path), run_once) == {"r1": "aborted"}
    frozen = _manifest(tmp_path, name="r2", config_hash="deadbeef0000")
    assert _execute(tmp_path, frozen, run_once) == {"r2": "aborted"}
    llm = _manifest(
        tmp_path, name="r3", config="config/experiments/e5_llm_sonnet.yaml", prompt_track="none"
    )
    assert _execute(tmp_path, llm, run_once) == {"r3": "aborted"}
    assert passes == []
    log = (res / "manifest-m.log").read_text()
    assert "config_hash" in log and "set prompt_track" in log


def test_dry_run_plans_without_running(tmp_path, monkeypatch):
    _dataset(tmp_path)
    run_once, passes = _fake_runner(tmp_path, {})
    assert _execute(tmp_path, _manifest(tmp_path), run_once, dry_run=True) == {"r1": "planned"}
    assert passes == []


def test_runner_resume_refuses_rows_of_another_version():
    from routing_study.eval.runner import Runner
    from routing_study.settings import Settings

    r = Runner(Settings(_env_file=None), split="dev", mode="routing-only", run_name="x")
    r.meta = {"config_hash": "a", "prompt_hash": "p", "catalog_hash": "c", "dataset_sha256": "d"}
    r.assert_same_version([{"config_hash": "a", "prompt_hash": "p"}])
    with pytest.raises(ValueError, match="config_hash"):
        r.assert_same_version([{"config_hash": "b"}])


def test_cli_run_manifest_dry_run(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from routing_study.cli import app

    monkeypatch.setattr("routing_study.cli.load_dotenv", lambda *a, **k: False)
    path = tmp_path / "m.yaml"
    path.write_text(
        "split: nosuchsplit\nresults_dir: " + str(tmp_path / "res") + "\nruns:\n"
        "  - {name: r1, config: config/experiments/e1_regex.yaml, mode: routing-only}\n"
    )
    res = CliRunner().invoke(app, ["run-manifest", str(path), "--dry-run"])
    assert res.exit_code == 1 and "ABORT r1" in res.output  # the split file does not exist


def test_langfuse_outage_stops_the_manifest_before_spending(tmp_path):
    from routing_study.tracing.langfuse import LangfuseUnavailableError

    _dataset(tmp_path)
    m = mf.Manifest(
        split="dev",
        results_dir=tmp_path / "results",
        runs=[
            {"name": "r1", "config": str(E1), "mode": "routing-only"},
            {"name": "r2", "config": str(E1), "mode": "routing-only"},
        ],
    )
    calls = []

    async def run_once(run, *_):
        calls.append(run.name)
        raise LangfuseUnavailableError("down")

    assert _execute(tmp_path, m, run_once) == {"r1": "langfuse"}
    assert calls == ["r1"] and not (tmp_path / "results" / "r1.jsonl").exists()


def test_resume_provenance_uses_the_catalog_content_hash():
    """Rows written by a process whose catalog came from another protocol era (same content)
    carry the same catalog_hash, so the resume assertion accepts them."""
    import sys

    from routing_study.eval.runner import Runner
    from routing_study.settings import Settings

    sys.path.insert(0, str(Path(__file__).parents[1] / "graph"))
    from graph_fakes import make_catalog

    cat = make_catalog()
    legacy = type(cat)(
        url=cat.url,
        protocol_version="2025-11-25",
        instructions=cat.instructions,
        tools=[dict(reversed(list(t.items()))) for t in cat.tools],
        skills=cat.skills,
    )
    r = Runner(Settings(_env_file=None), split="dev", mode="routing-only", run_name="x")
    r.meta = {"config_hash": "a", "prompt_hash": "p", "catalog_hash": cat.hash}
    r.meta["dataset_sha256"] = "d"
    r.assert_same_version([{"catalog_hash": legacy.hash}])
    with pytest.raises(ValueError, match="catalog_hash"):
        r.assert_same_version([{"catalog_hash": "823546e24af8"}])
