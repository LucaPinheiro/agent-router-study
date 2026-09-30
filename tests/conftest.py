"""Hermetic unit tests: no developer `.env`, no ambient config/OTel env (review B14).

Integration tests (`-m integration`) keep the real environment: they need the API keys.
"""

from __future__ import annotations

import os

import pytest

from routing_study.settings import Settings

_SETTINGS_ENV = {name.upper() for name in Settings.model_fields}  # MAX_RATE_LIMIT_WAIT_S, …
_PREFIXES = ("ROUTING__", "STRATEGIES__", "EXECUTOR__", "BUDGET__", "OTEL_", "LANGFUSE_")


@pytest.fixture(autouse=True)
def hermetic_env(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path_factory
) -> None:
    if request.node.get_closest_marker("integration"):
        return
    for key in list(os.environ):
        if key.upper() in _SETTINGS_ENV or key.upper().startswith(_PREFIXES):
            monkeypatch.delenv(key)
    # Settings(...) and load_settings(...) both read `env_file` from here at call time.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    # never append to the real spend ledger (results/spend_ledger.jsonl) from unit tests
    ledger = tmp_path_factory.mktemp("ledger") / "spend.jsonl"
    monkeypatch.setenv("BUDGET__LEDGER_PATH", str(ledger))
