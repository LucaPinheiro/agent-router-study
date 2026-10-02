"""Cascade threshold calibration (eval/calibrate.py, scripts/analysis/calibrate_cascades.py)
on synthetic shadow rows: the fast grid evaluator must equal `simulate_rows`."""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from routing_study.eval import calibrate as cal
from routing_study.eval.rescore import PROVENANCE
from routing_study.settings import PipelineStep, RoutingConfig, Settings, StageConfig

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "analysis"))

import calibrate_cascades  # noqa: E402

SKILLS = ("pedidos", "pagamentos", "trocas")
TOOLS = {"pedidos": ("track", "status"), "pagamentos": ("refund", "pix"), "trocas": ("swap",)}


def settings(
    skill: tuple[tuple[str, float | None], ...] = (("regex", 0.9), ("jev", 0.75), ("llm", None)),
    tool: tuple[tuple[str, float | None], ...] = (("jev", 0.7), ("llm", None)),
) -> Settings:
    def stage(steps: tuple[tuple[str, float | None], ...]) -> StageConfig:
        return StageConfig(pipeline=[PipelineStep(strategy=s, min_confidence=m) for s, m in steps])

    return Settings(
        _env_file=None,
        experiment_id="synthetic",
        routing=RoutingConfig(mode="cascade", skill=stage(skill), tool=stage(tool)),
    )


def dec(
    strategy: str, choice: str | None, conf: float, cost: float = 0.0, **usage: Any
) -> dict[str, Any]:
    return {
        "choice": choice,
        "confidence": conf,
        "candidates": [],
        "strategy": strategy,
        "latency_ms": 1.0,
        "cost_usd": cost,
        "usage": usage,
        "cached": False,
    }


COST = {"regex": 0.0, "jev": 0.0002, "llm": 0.003}


def random_rows(n: int, seed: int) -> list[dict[str, Any]]:
    """Mixed rows: right/wrong/abstaining steps, out-of-scope golds, failing steps, recorded
    skill different from what a cascade may pick (tool stage not replayable)."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        oos = rng.random() < 0.15
        gold = "__abstain__" if oos else rng.choice(SKILLS)
        tool = "__abstain__" if oos else rng.choice(TOOLS[gold])

        def pick_skill(p_right: float, gold: str = gold, oos: bool = oos) -> str | None:
            u = rng.random()
            if u < 0.1:
                return None
            if oos:
                return "__global__" if u < 0.5 else rng.choice(SKILLS)
            return gold if u < p_right else rng.choice([s for s in SKILLS if s != gold])

        sk = {}
        for s, p in (("regex", 0.7), ("jev", 0.85), ("llm", 0.92)):
            c = pick_skill(p)
            usage = {"error": "Timeout"} if c is None and s == "llm" and rng.random() < 0.3 else {}
            conf = round(rng.uniform(0.3, 1.0), 2) if c else 0.0
            sk[s] = dec(s, c, conf, COST[s], **usage)
        recorded = rng.choice([sk["regex"]["choice"], sk["jev"]["choice"], sk["llm"]["choice"]])
        row: dict[str, Any] = {
            "case_id": f"c{i:03d}",
            "rep": 1,
            "category": rng.choice(("direto", "parafrase", "ambiguo")),
            "expected": {
                "acceptable_skills": [gold],
                "acceptable_tools": [tool],
                "args": {},
            },
            "skill": {"choice": recorded, "shadow": sk},
        }
        if recorded and rng.random() < 0.9:
            options = [*TOOLS.get(recorded, ("x",)), "__abstain__"]
            tl = {}
            for s, p in (("jev", 0.8), ("llm", 0.9)):
                c = tool if rng.random() < p else rng.choice(options)
                if rng.random() < 0.05:
                    tl[s] = dec(s, None, 0.0, COST[s], parse_fail=True)
                else:
                    tl[s] = dec(s, c, round(rng.uniform(0.4, 1.0), 2), COST[s])
            row["tool"] = {"choice": tl["jev"]["choice"], "shadow": tl}
        rows.append(row)
    rows.append({"case_id": "nosh", "rep": 1, "category": "direto", "expected": {}, "skill": {}})
    return rows


def test_grid_default_is_050_to_099_by_001():
    g = cal.grid()
    assert len(g) == 50 and g[0] == 0.5 and g[-1] == 0.99 and 0.9 in g


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_fast_evaluator_matches_simulate_rows(seed):
    rows = random_rows(80, seed)
    s = settings()
    t = cal.build_tables(rows, s)
    rng = random.Random(seed)
    g = cal.grid(0.3, 1.0, 0.05)
    points = [cal.configured(s), ((0.0, 0.0), (0.0,)), ((1.01, 1.01), (1.01,))]
    points += [((rng.choice(g), rng.choice(g)), (rng.choice(g),)) for _ in range(25)]
    for sk, tl in points:
        cal.simulator_check(rows, s, t, sk, tl)  # raises on any mismatch


def test_grid_sums_match_single_point_evaluation():
    rows = random_rows(60, 5)
    t = cal.build_tables(rows, settings())
    g = cal.grid(0.5, 0.95, 0.15)
    gs = cal.grid_sums(t, cal.combos_of(g, 2), cal.combos_of(g, 1), max_cells=500)
    m = cal.metrics(gs.total())
    for a, sk in enumerate(gs.skill_combos):
        for b, tl in enumerate(gs.tool_combos):
            one = cal.metrics(cal.grid_sums(t, sk[None], tl[None]).total())
            assert one["n"][0, 0] == m["n"][a, b]
            assert np.isclose(one["joint_acc"][0, 0], m["joint_acc"][a, b])


def cheap_vs_expensive_rows() -> list[dict[str, Any]]:
    """regex is right iff conf >= 0.8 (else wrong), llm always right at a cost."""
    rows = []
    for i in range(40):
        conf = round(0.6 + 0.01 * i, 2)  # 0.60 .. 0.99
        right = i >= 20  # conf >= 0.80
        rows.append(
            {
                "case_id": f"c{i}",
                "rep": 1,
                "category": "direto" if i % 2 else "parafrase",
                "expected": {
                    "acceptable_skills": ["pedidos"],
                    "acceptable_tools": ["track"],
                    "args": {},
                },
                "skill": {
                    "choice": "pedidos",
                    "shadow": {
                        "regex": dec("regex", "pedidos" if right else "trocas", conf),
                        "llm": dec("llm", "pedidos", 0.9, 0.01),
                    },
                },
                "tool": {"choice": "track", "shadow": {"llm": dec("llm", "track", 0.9, 0.001)}},
            }
        )
    return rows


def two_step() -> Settings:
    return settings(skill=(("regex", 0.9), ("llm", None)), tool=(("llm", None),))


def test_budget_selection_and_pareto_front():
    rows = cheap_vs_expensive_rows()
    t = cal.build_tables(rows, two_step())
    g = cal.grid()
    gs = cal.grid_sums(t, cal.combos_of(g, 1), cal.combos_of(g, 0))
    # unconstrained: 100% at the cheapest threshold that sends every wrong regex to the LLM
    assert cal.select_budget(gs, None) == ((0.8,), ())
    # the budget forbids escalating everything below 0.8: accuracy is traded for cost
    sk, _ = cal.select_budget(gs, 0.0025)
    m = cal.metrics(cal.grid_sums(t, np.array([sk]), np.zeros((1, 0))).total())
    assert m["cost"][0, 0] <= 0.0025 and m["joint_acc"][0, 0] < 1.0
    assert cal.select_budget(gs, 0.0) is None  # the tool LLM alone costs more
    front = cal.pareto_front(gs)
    costs = [p["cost"] for p in front]
    accs = [p["joint_acc"] for p in front]
    assert costs == sorted(costs) and accs == sorted(accs) and len(set(accs)) == len(accs)
    assert front[-1]["joint_acc"] == 1.0 and front[-1]["skill"] == (0.8,)


def test_precision_rule_picks_lowest_threshold_meeting_next_step_precision():
    rows = cheap_vs_expensive_rows()
    t = cal.build_tables(rows, two_step())
    (step,) = cal.precision_rule(t, "skill", ["regex"], cal.grid(), min_support=5)
    assert step.target == 1.0 and step.threshold == 0.8 and step.precision == 1.0
    assert step.accepted == 20
    # a weaker next step (35/40) lowers the bar: at 0.78 regex is 20/22 right, at 0.77 20/23
    for r in rows[:5]:
        r["skill"]["shadow"]["llm"]["choice"] = "trocas"
    t = cal.build_tables(rows, two_step())
    (step,) = cal.precision_rule(t, "skill", ["regex"], cal.grid(), min_support=5)
    assert step.target == pytest.approx(35 / 40)
    assert (step.threshold, step.accepted) == (0.78, 22)
    # regex never as good as the next step: no threshold, reported as 'never'
    for r in rows:
        r["skill"]["shadow"]["regex"]["choice"] = "trocas"
    t = cal.build_tables(rows, two_step())
    (step,) = cal.precision_rule(t, "skill", ["regex"], cal.grid())
    assert step.threshold is None and cal.rule_thresholds([step]) == (1.01,)


def test_ever_error_fixes_the_denominator():
    rows = cheap_vs_expensive_rows()
    rows[0]["skill"]["shadow"]["llm"] = dec("llm", None, 0.0, 0.01, error="Timeout")
    t = cal.build_tables(rows, two_step())
    g = cal.grid()
    bad = cal.ever_error(t, cal.combos_of(g, 1), cal.combos_of(g, 0))
    assert bad.tolist() == [True] + [False] * 39


def test_folds_are_stratified_and_deterministic():
    cats = {f"{c}-{i}": c for c in ("a", "b") for i in range(10)}
    folds = cal.folds_of(cats, 5, seed=0)
    assert folds == cal.folds_of(cats, 5, seed=0)
    for c in ("a", "b"):
        assert Counter(f for k, f in folds.items() if k.startswith(c)) == dict.fromkeys(range(5), 2)


def test_crossval_scores_every_row_once_on_its_held_out_fold():
    rows = cheap_vs_expensive_rows()
    t = cal.build_tables(rows, two_step())
    g = cal.grid()
    fold = cal.folds_of({r["case_id"]: r["category"] for r in rows}, 4, seed=0)
    groups = np.array([fold[c] for c in t.case_ids])
    gs = cal.grid_sums(t, cal.combos_of(g, 1), cal.combos_of(g, 0), groups)
    held, picks = cal.crossval(t, fold, lambda f: cal.select_budget(gs, None, exclude=f))
    assert sorted(h["case_id"] for h in held) == sorted(r["case_id"] for r in rows)
    assert len(picks) == 4 and all(p is not None for p in picks)
    s = cal.summarize(held)
    assert s["n"] == 40 and s["joint_ci"] is not None and s["cost_ci"] is not None


def test_with_thresholds_keeps_the_last_step():
    s = cal.with_thresholds(settings(), (0.5, 0.6), (0.7,))
    assert [p.min_confidence for p in s.routing.skill.pipeline] == [0.5, 0.6, None]
    assert [p.min_confidence for p in s.routing.tool.pipeline] == [0.7, None]
    assert cal.tuned_steps(s.routing.skill, "cascade") == ["regex", "jev"]
    assert cal.configured(settings()) == ((0.9, 0.75), (0.7,))


def test_script_writes_report_yaml_and_csv(tmp_path, monkeypatch):
    rows = random_rows(60, 3)
    prov = {
        "source": {"file": "shadow-dev.jsonl", "rows": len(rows)},
        "dataset": {"split": "dev", "file": "dataset_dev.jsonl", "sha256": "0" * 64},
        "scorer_hash": "abc",
        "run_git_sha": "unknown",
    }
    shadow = tmp_path / "shadow-dev.jsonl"
    shadow.write_text(
        "\n".join(json.dumps(x) for x in [{PROVENANCE: prov}, *rows]) + "\n", encoding="utf-8"
    )
    cfg = tmp_path / "e9_synthetic.yaml"
    cfg.write_text(
        "routing:\n  mode: cascade\n  skill:\n    pipeline:\n"
        "      - { strategy: regex, min_confidence: 0.9 }\n"
        "      - { strategy: jev, min_confidence: 0.75 }\n      - { strategy: llm }\n"
        "  tool:\n    pipeline:\n      - { strategy: jev, min_confidence: 0.7 }\n"
        "      - { strategy: llm }\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    argv = [str(shadow), "--config", str(cfg), "--out-dir", str(out), "--grid", "0.5", "0.95"]
    monkeypatch.setattr(sys, "argv", ["calibrate_cascades.py", *argv, "0.05", "--folds", "3"])
    calibrate_cascades.main()
    report = (out / "calibration.md").read_text(encoding="utf-8")
    assert "## e9_synthetic" in report and "(a) max joint" in report and "(b) precision" in report
    assert "oracle (best stopping step per row)" in report and "random deferral at" in report
    snippet = __import__("yaml").safe_load((out / "thresholds.yaml").read_text(encoding="utf-8"))
    pipe = snippet["e9_synthetic"]["budget"]["routing"]["skill"]["pipeline"]
    assert pipe[-1] == {"strategy": "llm"}
    assert all(0.5 <= p["min_confidence"] <= 0.95 for p in pipe[:-1])
    lines = (out / "pareto.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("experiment,skill_thresholds") and len(lines) > 1


def test_references_oracle_bounds_every_grid_point_and_random_matches_rates():
    st = settings()
    rows = [r for r in random_rows(80, 5) if r["skill"]]
    t = cal.build_tables(rows, st)
    g = cal.grid(0.5, 0.95, 0.05)
    gs = cal.grid_sums(t, cal.combos_of(g, 2), cal.combos_of(g, 1))
    best = max(p["joint_acc"] for p in cal.pareto_front(gs))
    oracle = cal.summarize(calibrate_cascades.oracle_rows(t))["joint_ci"][0]
    assert oracle >= best - 1e-9
    # rates 1.0 everywhere (thresholds 0) = always-first; 0 everywhere = always-last
    first = cal.summarize(cal.row_values(t, (0.0, 0.0), (0.0,)))["joint_ci"][0]
    rd = calibrate_cascades.random_deferral(t, ((0.0, 0.0), (0.0,)), 3, 0)
    assert abs(rd["joint"] - 100 * first) < 1e-6
    last = cal.summarize(cal.row_values(t, (1.01, 1.01), (1.01,)))["joint_ci"][0]
    rd = calibrate_cascades.random_deferral(t, ((1.01, 1.01), (1.01,)), 3, 0)
    assert abs(rd["joint"] - 100 * last) < 1e-6


def test_script_refuses_a_non_dev_split(tmp_path, monkeypatch):
    prov = {"source": {"file": "x", "rows": 0}, "dataset": {"split": "test"}}
    shadow = tmp_path / "shadow-test.jsonl"
    shadow.write_text(json.dumps({PROVENANCE: prov}) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["calibrate_cascades.py", str(shadow)])
    with pytest.raises(SystemExit, match="dev only"):
        calibrate_cascades.main()


def test_f2_itt_counts_error_rows_as_wrong_in_the_grid_and_the_summary():
    rows = cheap_vs_expensive_rows()
    rows[0]["skill"]["shadow"]["llm"] = dec("llm", None, 0.0, 0.01, error="Timeout")
    t = cal.build_tables(rows, two_step())
    # threshold 0.99: row 0 (regex conf 0.60) reaches the failing LLM -> an error row
    m = cal.metrics(cal.grid_sums(t, np.array([[0.99]]), np.zeros((1, 0))).total())
    assert m["n"][0, 0] == 40 and m["errors"][0, 0] == 1 and m["n_ok"][0, 0] == 39
    assert m["joint_acc"][0, 0] == pytest.approx(39 / 40)  # the error counts as wrong
    assert m["joint_acc_error_free"][0, 0] == 1.0
    s = cal.summarize(cal.row_values(t, (0.99,), ()))
    assert s["n"] == 40 and s["errors"] == 1 and s["joint_ci"][0] == pytest.approx(39 / 40)
