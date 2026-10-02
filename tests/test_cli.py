"""`study` CLI argument validation (no network)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from routing_study.cli import app


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI callback loads `.env` into os.environ; keep the test process hermetic."""
    monkeypatch.setattr("routing_study.cli.load_dotenv", lambda *a, **k: False)


def test_run_rejects_unknown_routing_mode():
    """B12: a typo'd --routing-mode must fail at parse time, not mid-run."""
    res = CliRunner().invoke(
        app,
        ["run", "--config", "config/experiments/e9_regex_jev_llm.yaml", "--routing-mode", "shadw"],
    )
    assert res.exit_code == 2
    assert "shadw" in res.output


def test_run_rejects_unknown_mode():
    res = CliRunner().invoke(
        app, ["run", "--config", "config/experiments/e9_regex_jev_llm.yaml", "--mode", "e3e"]
    )
    assert res.exit_code == 2


def test_report_requires_explicit_runs_or_a_manifest():
    """F7: no implicit whole-directory report."""
    res = CliRunner().invoke(app, ["report"])
    assert res.exit_code != 0
    assert "paths" in res.output or "manifest" in res.output
