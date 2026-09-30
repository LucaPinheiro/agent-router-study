"""Calibrate cascade thresholds on the DEV split from a RESCORED shadow run (docs/calibration.md).

Usage:
  uv run python scripts/analysis/calibrate_cascades.py <rescored shadow dev.jsonl> \\
      [--config config/experiments/e7_regex_jev.yaml ...] [--budget 0.0005] \\
      [--folds 5] [--seed 0] [--grid 0.50 0.99 0.01] [--min-support 5] \\
      [--out-dir results/calibration]

For each cascade (default E7, E8, E9; `--config` replaces the list) it picks the non-last
steps' `min_confidence` per stage with two methods (src/routing_study/eval/calibrate.py):
  (a) max joint accuracy s.t. routing cost/case <= --budget (unconstrained without it), over
      the full grid, plus the accuracy-vs-cost Pareto front;
  (b) precision rule: accept a cheap step when its precision on the cases it accepts is >= the
      next step's overall precision.
Both are re-fitted inside a stratified k-fold CV (by category, over case ids, fixed seed) and
scored on the held-out folds, with 95% cluster-bootstrap CIs (`eval/stats.py`). No API call:
everything is replayed from the recorded decisions and scored by the shared scorer; the fast
grid evaluator is cross-checked against `eval/simulate.simulate_rows` at every reported point.

Writes <out-dir>/calibration.md (report), thresholds.yaml (snippet per experiment, NOT applied
to config/experiments) and pareto.csv (front per experiment, for plotting).
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from routing_study.eval import calibrate as cal
from routing_study.eval.rescore import read_rescored
from routing_study.eval.stats import fmt_ci
from routing_study.settings import load_settings

DEFAULT_CONFIGS = [
    Path(f"config/experiments/{c}.yaml")
    for c in ("e7_regex_jev", "e8_regex_llm", "e9_regex_jev_llm")
]
MAX_COMBOS = 5_000_000
NEVER = 1.01  # rule (b): no grid value met the target -> the step never accepts


def fmt_th(names: list[str], ts: tuple[float, ...]) -> str:
    if not names:
        return "-"
    return ", ".join(
        f"{n}={'never' if t > 1.0 else f'{t:.2f}'}" for n, t in zip(names, ts, strict=True)
    )


def stage_yaml(stage: Any, mode: str, ts: tuple[float, ...]) -> dict[str, Any]:
    """A stage's pipeline with the calibrated thresholds; a rule (b) 'never' step is left out
    (it would only add cost: it never accepts)."""
    steps = []
    for i, s in enumerate(cal.steps_of(stage, mode)):
        t = ts[i] if i < len(ts) else s.min_confidence
        if t is not None and t > 1.0:
            continue
        step: dict[str, Any] = {"strategy": s.strategy}
        if t is not None:
            step["min_confidence"] = round(float(t), 4)
        steps.append(step)
    return {"pipeline": steps}


def calibrate_config(
    path: Path,
    rows: list[dict[str, Any]],
    fold: dict[str, int],
    args: argparse.Namespace,
) -> dict[str, Any]:
    settings = load_settings(path)
    name = path.stem
    mode = settings.routing.mode
    sk_names = cal.tuned_steps(settings.routing.skill, mode)
    tl_names = cal.tuned_steps(settings.routing.tool, mode)
    if not sk_names and not tl_names:
        return {"name": name, "skipped": "no cascade step to calibrate (single-step pipelines)"}
    g = cal.grid(*args.grid)
    n_combos = len(g) ** (len(sk_names) + len(tl_names))
    if n_combos > MAX_COMBOS:
        return {"name": name, "skipped": f"{n_combos} combos > {MAX_COMBOS}: coarsen --grid"}
    skill_combos, tool_combos = cal.combos_of(g, len(sk_names)), cal.combos_of(g, len(tl_names))
    t_all = cal.build_tables(rows, settings)
    keep = ~cal.ever_error(t_all, skill_combos, tool_combos)
    rows = [r for r, k in zip(rows, keep, strict=True) if k]
    t = cal.build_tables(rows, settings)
    groups = np.array([fold[c] for c in t.case_ids])
    gs = cal.grid_sums(t, skill_combos, tool_combos, groups)

    def rule(mask: np.ndarray | None) -> tuple[list[cal.RuleStep], list[cal.RuleStep]]:
        kw = {"mask": mask, "min_support": args.min_support}
        return (
            cal.precision_rule(t, "skill", sk_names, g, **kw),
            cal.precision_rule(t, "tool", tl_names, g, **kw),
        )

    def rule_pick(steps: tuple[list[cal.RuleStep], list[cal.RuleStep]]) -> Any:
        return tuple(cal.rule_thresholds(s, NEVER) for s in steps)

    rule_steps = rule(None)
    choices = {
        "configured (YAML)": cal.configured(settings),
        "(a) max joint s.t. budget": cal.select_budget(gs, args.budget),
        "(b) precision rule": rule_pick(rule_steps),
    }
    selectors = {
        "(a) max joint s.t. budget": lambda f: cal.select_budget(gs, args.budget, exclude=f),
        "(b) precision rule": lambda f: rule_pick(rule(groups != f)),
    }
    methods = []
    checked = 0
    for label, pick in choices.items():
        entry: dict[str, Any] = {"label": label, "pick": pick}
        if pick is not None:
            cal.simulator_check(rows, settings, t, *pick)
            checked += 1
            entry["dev"] = cal.summarize(cal.row_values(t, *pick))
        if label in selectors:
            held, picks = cal.crossval(t, fold, selectors[label])
            entry["cv"] = cal.summarize(held)
            entry["cv_picks"] = Counter(
                "-" if p is None else f"{fmt_th(sk_names, p[0])} / {fmt_th(tl_names, p[1])}"
                for p in picks
            )
        methods.append(entry)
    front = cal.pareto_front(gs)
    rng = random.Random(args.seed)
    points = [(p["skill"], p["tool"]) for p in front]
    points += [
        (tuple(rng.choice(g) for _ in sk_names), tuple(rng.choice(g) for _ in tl_names))
        for _ in range(args.checks)
    ]
    for p in points:
        cal.simulator_check(rows, settings, t, *p)
    return {
        "name": name,
        "settings": settings,
        "sk_names": sk_names,
        "tl_names": tl_names,
        "combos": n_combos,
        "rows": len(rows),
        "excluded": int((~keep).sum()),
        "methods": methods,
        "rule_steps": rule_steps[0] + rule_steps[1],
        "front": front,
        "checked": checked + len(points),
    }


def calibrated_share(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """(lexical decisions carrying usage.raw_confidence, lexical decisions): 0 means the run
    predates the confidence calibration maps, so its thresholds are on the raw scale."""
    decisions = [
        d
        for r in rows
        for lv in ("skill", "tool")
        for s, d in ((r.get(lv) or {}).get("shadow") or {}).items()
        if s in ("regex", "bm25") and d.get("choice")
    ]
    return sum("raw_confidence" in (d.get("usage") or {}) for d in decisions), len(decisions)


def render(
    results: list[dict[str, Any]],
    prov: dict[str, Any],
    args: argparse.Namespace,
    calibrated: tuple[int, int],
) -> str:
    g = cal.grid(*args.grid)
    budget = "none (max joint accuracy)" if args.budget is None else f"US$ {args.budget:g}/case"
    out = [
        f"# Cascade threshold calibration: {args.shadow.name}\n",
        f"- source: {prov['source']['file']} ({prov['source']['rows']} rows), dataset "
        f"{prov['dataset']['file']} {prov['dataset']['sha256'][:12]}, scorer "
        f"{prov['scorer_hash']}, run git {prov['run_git_sha']}",
        f"- grid {g[0]:.2f}..{g[-1]:.2f} ({len(g)} values) per non-last step; budget {budget}; "
        f"{args.folds}-fold CV stratified by category over case ids, seed {args.seed}; rule (b) "
        f"min support {args.min_support} accepted cases",
        "- every number of an experiment is over the rows that are error-free at EVERY grid "
        "point (fixed denominator: a threshold cannot win by routing failing cases into an "
        "error); joint %: a tool stage that cannot be replayed (simulated skill "
        "differs from the recorded one) counted 0 (lower bound); US$/1k routing cost over covered "
        "rows; 95% CIs: cluster bootstrap over case ids (`eval/stats.py`, fixed seed)",
        "- 'dev' = fitted and scored on all dev rows (optimistic); 'CV held-out' = re-fitted on "
        "k-1 folds, scored on the held-out fold, pooled",
        f"- confidences as recorded: {calibrated[0]}/{calibrated[1]} regex/BM25 decisions carry "
        "`usage.raw_confidence` (0 = the run predates the calibration maps: its thresholds are "
        "on the raw scale; re-run the shadow run with the current config before applying them)",
    ]
    for r in results:
        out.append(f"\n## {r['name']}\n")
        if "skipped" in r:
            out.append(f"skipped: {r['skipped']}")
            continue
        st = r["settings"].routing
        mode = st.mode
        chain = {
            lv: " -> ".join(s.strategy for s in cal.steps_of(getattr(st, lv), mode))
            for lv in ("skill", "tool")
        }
        out.append(
            f"skill: {chain['skill']} | tool: {chain['tool']} | {r['combos']} combos | "
            f"{r['rows']} rows error-free at every grid point ({r['excluded']} excluded) | "
            f"fast evaluator == simulate_rows at {r['checked']} points\n"
        )
        out.append(
            "| method | skill thresholds | tool thresholds | dev joint % | dev US$/1k "
            "| CV held-out joint % | CV US$/1k | picks per fold |"
        )
        out.append("|---|---|---|---|---|---|---|---|")
        for m in r["methods"]:
            p = m["pick"]
            if p is None:
                out.append(f"| {m['label']} | infeasible | | | | | | |")
                continue
            dev, cv = m["dev"], m.get("cv")
            picks = "; ".join(f"{k} x{v}" for k, v in m.get("cv_picks", {}).items()) or "(no fit)"
            out.append(
                f"| {m['label']} | {fmt_th(r['sk_names'], p[0])} | {fmt_th(r['tl_names'], p[1])} "
                f"| {fmt_ci(dev['joint_ci'])} | {fmt_ci(dev['cost_ci'], scale=1000.0, digits=4)} "
                f"| {fmt_ci(cv['joint_ci']) if cv else '= dev (no fit)'} "
                f"| {fmt_ci(cv['cost_ci'], scale=1000.0, digits=4) if cv else '= dev'} "
                f"| {picks} |"
            )
        out.append("\nRule (b) on all dev rows:\n")
        out.append(
            "| stage | step | target = next step's precision | threshold "
            "| precision of accepted | accepted n |"
        )
        out.append("|---|---|---|---|---|---|")
        for s in r["rule_steps"]:
            target = "-" if s.target is None else f"{100 * s.target:.1f}%"
            prec = "-" if s.precision is None else f"{100 * s.precision:.1f}%"
            th = "never (drop step)" if s.threshold is None else f"{s.threshold:.2f}"
            out.append(f"| {s.stage} | {s.strategy} | {target} | {th} | {prec} | {s.accepted} |")
        out.append(f"\nPareto front on dev ({len(r['front'])} points; pareto.csv):\n")
        out.append(
            "| skill thresholds | tool thresholds | joint % | joint cov. % | US$/1k "
            "| n | err | unavail |"
        )
        out.append("|---|---|---|---|---|---|---|---|")
        for p in r["front"]:
            out.append(
                f"| {fmt_th(r['sk_names'], p['skill'])} | {fmt_th(r['tl_names'], p['tool'])} "
                f"| {100 * p['joint_acc']:.1f} | {100 * p['joint_acc_covered']:.1f} "
                f"| {1000 * p['cost']:.4f} | {p['n']} | {p['errors']} | {p['unavail']} |"
            )
    return "\n".join(out) + "\n"


def thresholds_yaml(results: list[dict[str, Any]], prov: dict[str, Any], budget: Any) -> str:
    doc: dict[str, Any] = {}
    for r in results:
        if "skipped" in r:
            continue
        routing = r["settings"].routing
        doc[r["name"]] = {}
        for m in r["methods"][1:]:
            if m["pick"] is None:
                continue
            key = "budget" if m["label"].startswith("(a)") else "precision_rule"
            doc[r["name"]][key] = {
                "routing": {
                    lv: stage_yaml(getattr(routing, lv), routing.mode, m["pick"][i])
                    for i, lv in enumerate(("skill", "tool"))
                }
            }
    head = (
        f"# Cascade thresholds calibrated on dev: {prov['source']['file']} "
        f"(dataset {prov['dataset']['sha256'][:12]}, scorer {prov['scorer_hash']}).\n"
        f"# budget = (a) max joint accuracy s.t. routing cost/case <= "
        f"{'unconstrained' if budget is None else f'US$ {budget:g}'}; "
        "precision_rule = (b). Generated by scripts/analysis/calibrate_cascades.py;\n"
        "# copy the chosen block's `routing.*.pipeline` into config/experiments/<name>.yaml.\n"
    )
    return head + yaml.safe_dump(doc, sort_keys=False, default_flow_style=None, width=100)


def write_csv(results: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "experiment",
        "skill_thresholds",
        "tool_thresholds",
        "joint_acc",
        "joint_acc_covered",
        "skill_acc",
        "cost_usd_case",
        "cost_usd_per_1k",
        "n",
        "errors",
        "tool_unavailable",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in results:
            for p in r.get("front", []):
                w.writerow(
                    {
                        "experiment": r["name"],
                        "skill_thresholds": fmt_th(r["sk_names"], p["skill"]),
                        "tool_thresholds": fmt_th(r["tl_names"], p["tool"]),
                        "joint_acc": round(p["joint_acc"], 6),
                        "joint_acc_covered": round(p["joint_acc_covered"], 6),
                        "skill_acc": round(p["skill_acc"], 6),
                        "cost_usd_case": f"{p['cost']:.6e}",
                        "cost_usd_per_1k": round(1000 * p["cost"], 6),
                        "n": p["n"],
                        "errors": p["errors"],
                        "tool_unavailable": p["unavail"],
                    }
                )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("shadow", type=Path, help="rescored shadow run on the dev split")
    ap.add_argument("--config", type=Path, nargs="+", default=DEFAULT_CONFIGS)
    ap.add_argument("--budget", type=float, default=None, help="max routing US$ per case")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--grid", type=float, nargs=3, default=[0.50, 0.99, 0.01])
    ap.add_argument("--min-support", type=int, default=5)
    ap.add_argument("--checks", type=int, default=5, help="extra random simulator checks")
    ap.add_argument("--out-dir", type=Path, default=Path("results/calibration"))
    args = ap.parse_args()

    prov, rows = read_rescored(args.shadow)
    if prov["dataset"]["split"] != "dev":
        raise SystemExit(f"thresholds are calibrated on dev only, got {prov['dataset']['split']}")
    if not any((r.get("skill") or {}).get("shadow") for r in rows):
        raise SystemExit(f"{args.shadow} has no shadow decisions (run with --routing-mode shadow)")
    fold = cal.folds_of(
        {r["case_id"]: r.get("category") or "" for r in rows}, args.folds, args.seed
    )
    results = [calibrate_config(p, rows, fold, args) for p in args.config]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = render(results, prov, args, calibrated_share(rows))
    (args.out_dir / "calibration.md").write_text(report, encoding="utf-8")
    (args.out_dir / "thresholds.yaml").write_text(
        thresholds_yaml(results, prov, args.budget), encoding="utf-8"
    )
    write_csv(results, args.out_dir / "pareto.csv")
    print(report)
    print(f"wrote {args.out_dir}/calibration.md, thresholds.yaml, pareto.csv")


if __name__ == "__main__":
    main()
