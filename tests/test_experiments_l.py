"""Large-catalog host wiring (T3.3): config/experiments_l/ and the manifest catalog_hash guard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from routing_study.eval import manifest as manifest_mod
from routing_study.eval.manifest import ManifestRun, version_problems
from routing_study.routers.regex import RegexRules
from routing_study.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]
CONFIGS_L = sorted((ROOT / "config" / "experiments_l").glob("*.yaml"))
LARGE_URL = "http://localhost:8766/mcp"


@pytest.fixture(autouse=True)
def _repo_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)


def test_large_configs_exist() -> None:
    names = {p.stem for p in CONFIGS_L}
    assert {"e0_native_l", "e9_regex_jev_llm_l", "e3_embedding_l", "e10_classifier_l"} <= names
    assert not any("qwen" in n or "bgem3" in n for n in names)  # no local model in phase 2


@pytest.mark.parametrize("path", CONFIGS_L, ids=[p.stem for p in CONFIGS_L])
def test_large_config_wiring(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_URL", "http://localhost:8765/mcp")  # the .env value: must not win
    settings = load_settings(path)
    assert settings.mcp_url == LARGE_URL
    dumped = settings.model_dump(mode="json", include={"routing", "strategies", "executor"})
    text = json.dumps(dumped)
    assert '"ollama"' not in text and "llm_local" not in text  # no local provider anywhere
    for name, block in (dumped["strategies"] or {}).items():
        if isinstance(block, dict) and block.get("provider") == "openrouter":
            assert name == "jev", f"{path.name}: only Jev may run on OpenRouter ({name})"
    if (regex := settings.strategies.regex) is not None:
        assert regex.rules_path == "config/regex_rules_l.yaml"
    if (emb := settings.strategies.embedding) is not None:
        # T5: Titan v2 is the large-profile embedder (Part A: ties Cohere, ~4x faster, ~6x cheaper)
        assert emb.provider == "bedrock" and emb.model == "amazon.titan-embed-text-v2:0"


def test_explicit_override_still_wins_over_the_config_url() -> None:
    settings = load_settings(CONFIGS_L[0], mcp_url="http://elsewhere:1/mcp")
    assert settings.mcp_url == "http://elsewhere:1/mcp"


def test_phase1_configs_keep_the_env_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_URL", "http://localhost:8765/mcp")
    assert load_settings("config/experiments/e0_native.yaml").mcp_url.endswith(":8765/mcp")


def test_regex_rules_stub_loads() -> None:
    rules = RegexRules.load("config/regex_rules_l.yaml")
    assert rules is not None


def _run(**kw: object) -> ManifestRun:
    return ManifestRun(
        name="smoke", config=Path("config/experiments_l/e0_native_l.yaml"), mode="e2e", **kw
    )


def test_manifest_catalog_hash_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings("config/experiments_l/e0_native_l.yaml")
    calls: list[str] = []

    def served(s: object) -> str:
        calls.append(s.mcp_url)  # type: ignore[attr-defined]
        return "aaaaaaaaaaaa"

    monkeypatch.setattr(manifest_mod, "current_catalog_hash", served)
    assert version_problems(_run(), settings, "dev_l") == [] and calls == []  # optional
    assert version_problems(_run(catalog_hash="aaaaaaaaaaaa"), settings, "dev_l") == []
    problems = version_problems(_run(catalog_hash="128584617807"), settings, "dev_l")
    assert len(problems) == 1 and "catalog_hash aaaaaaaaaaaa" in problems[0]
    assert calls == [LARGE_URL, LARGE_URL]

    def down(s: object) -> str:
        raise OSError("connection refused")

    monkeypatch.setattr(manifest_mod, "current_catalog_hash", down)
    problems = version_problems(_run(catalog_hash="aaaaaaaaaaaa"), settings, "dev_l")
    assert problems and "unavailable" in problems[0]
