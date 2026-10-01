"""apply_prompt_selection.py (variant + calibration per track) and select_prompts.py rules."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "analysis"))

import apply_prompt_selection as aps  # noqa: E402
import select_prompts as sp  # noqa: E402

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


def test_one_se_rule_prefers_simpler_then_cheaper_and_p0_on_ties():
    order = ["P0", "P0+P3", "P0+P6c", "P0+P1+P3"]
    cost = {"P0": 5.0, "P0+P3": 5.1, "P0+P6c": 3.9, "P0+P1+P3": 5.5}
    scores = {
        "P0": [0.70, 0.72, 0.68, 0.71, 0.69],
        "P0+P3": [0.80, 0.82, 0.78, 0.81, 0.79],
        "P0+P6c": [0.80, 0.82, 0.79, 0.81, 0.80],
        "P0+P1+P3": [0.90, 0.75, 0.88, 0.76, 0.86],  # SE 0.031
    }
    chosen, best = sp.one_se(scores, cost, order)
    assert best == "P0+P1+P3"
    assert chosen == "P0+P6c"  # within 1 SE, one modifier, cheaper than P0+P3
    tie = {v: [0.8] * 5 for v in order}
    assert sp.one_se(tie, cost, order)[0] == "P0"  # simplest wins even when not cheapest


def test_nested_scores_each_fold_with_the_choice_made_on_the_others():
    scores = {"P0": [0.8, 0.8, 0.8, 0.8, 0.8], "P0+P3": [1.0, 0.6, 1.0, 1.0, 1.0]}
    held, picks = sp.nested(scores, {"P0": 1.0, "P0+P3": 1.0}, ["P0", "P0+P3"])
    assert len(held) == len(picks) == 5
    assert picks[1] == "P0+P3" and held[1] == 0.6  # chosen on folds 0,2,3,4


def test_subset_pruning_uses_error_free_cases_and_keeps_p0():
    def pts(vals, err=()):
        return {
            "records": {
                f"c{i}": {"joint_correct": float(v), "error": i in err} for i, v in enumerate(vals)
            },
            "metrics": {"errors": len(err)},
        }

    sub = {
        "P0": pts([1, 1, 0, 0, 1, 1, 1, 0]),
        "P0+P3": pts([1, 1, 1, 1, 1, 1, 1, 1]),
        "P0+P4": pts([0, 0, 0, 0, 0, 0, 1, 1], err=(0, 1)),  # errors drop cases 0,1 for all
    }
    out = sp.prune_subset(sub)
    assert out["P0"]["n_clean"] == 6
    assert out["P0"]["pruned"] is False
    assert out["P0+P4"]["pruned"] is True
    assert out["P0+P3"]["pruned"] is False
