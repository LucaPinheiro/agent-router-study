"""scripts/analysis/apply_prompt_selection.py: per-model variant + calibration per track."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "analysis"))

import apply_prompt_selection as aps  # noqa: E402

CONFIG = """routing:
  mode: single
strategies:
  llm:       { provider: bedrock, model: sonnet, temperature: null }  # no temperature
  llm_local: { provider: ollama, model: "qwen3:8b", num_ctx: 8192 }
  jev:       { provider: openrouter, model: jev }
  hybrid:    { rrf_k: 60 }
"""
SELECTION = {
    "sonnet": {
        "canonical": {"variant": "P0", "calibration": {"skill": {"x": [0.5], "y": [0.9]}}},
        "tuned": {"variant": "P0+P3"},
    },
    "jev": {"canonical": {"variant": "P0"}, "tuned": {"variant": "P0+P6c"}},
}


def test_apply_sets_track_variant_and_calibration_per_model():
    out = aps.apply(CONFIG, "tuned", SELECTION)
    s = yaml.safe_load(out)["strategies"]
    assert s["llm"] == {
        "provider": "bedrock",
        "model": "sonnet",
        "temperature": None,
        "prompt_track": "tuned",
        "prompt_variant": "P0+P3",
    }
    assert s["jev"]["prompt_variant"] == "P0+P6c"
    assert s["llm_local"] == {"provider": "ollama", "model": "qwen3:8b", "num_ctx": 8192}
    assert s["hybrid"] == {"rrf_k": 60}
    assert "  llm:  # no temperature\n" in out  # the line comment survives


def test_apply_is_idempotent_and_switches_tracks():
    canonical = aps.apply(CONFIG, "canonical", SELECTION)
    assert aps.apply(canonical, "canonical", SELECTION) == canonical
    s = yaml.safe_load(canonical)["strategies"]
    assert s["llm"]["calibration"] == {"skill": {"x": [0.5], "y": [0.9]}}
    back = yaml.safe_load(aps.apply(canonical, "tuned", SELECTION))["strategies"]
    assert back["llm"]["prompt_variant"] == "P0+P3" and "calibration" not in back["llm"]
