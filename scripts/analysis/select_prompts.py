"""Router prompt selection (D6): tuned + canonical track per model from tune_router `--out` JSON.

Usage:
  uv run python scripts/analysis/select_prompts.py \\
      --runs "Sonnet 5=global.anthropic.claude-sonnet-5" results/prompt_apex_v2/e5_*.json \\
      --runs "Haiku 4.5=global.anthropic.claude-haiku-4-5-20251001-v1:0" results/.../e6_*.json \\
      --runs "Jev=typesafe/jev-router" results/prompt_apex_v2/e4_*.json \\
      [--out config/prompt_selection.yaml] [--md docs/results/prompt-selection.md]

Re-computable: append `--runs "Qwen3-8B=qwen3:8b-q8_0" <files>` and re-run; the canonical
choice is recomputed over every model given.

Rules (pre-declared, .omc/plans/final-study-master.md D6):
- dev only; folds = tune_router.folds_of (5-fold, stratified by category, seed 0), rebuilt from
  the case ids/categories inside the records (the dev file is not re-read);
- a failed routing stage is an error scored wrong (ITT); a variant with > 2% failed rows is
  flagged (retry its cases before trusting it);
- subset pruning (n=60 points): on the cases error-free for every subset variant, a variant is
  pruned only when its paired joint difference to the subset leader is < -1 SE (never P0)
  (SE = sd(per-case difference) / sqrt(n));
- one-SE rule on full dev: best = highest CV joint mean; candidates = variants whose mean is
  >= best - SE(best) (SE = fold sd / sqrt(k)); pick the simplest (fewest modifier tokens on
  top of P0), then the cheapest per 1k cases, then grid order (P0 first: a tie goes to P0);
- tuned track: the rule per model; honest estimate = nested CV (the rule applied on the 4
  training folds, scored on the held-out fold);
- canonical track: the rule on the per-fold MEAN over models, among variants run on full dev
  for every model; nested estimate the same way;
- calibration per model x track x stage: isotonic map fitted on all dev (written), ECE raw ->
  calibrated measured cross-fitted (map fitted on 4 folds, applied to the held-out fold).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import mean, pstdev, stdev
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tune_router import LEVELS, folds_of, pairs  # noqa: E402

from routing_study.routers.calibration import ece, fit_isotonic  # noqa: E402

FOLDS, SEED = 5, 0
ERROR_LIMIT = 0.02
Recs = dict[str, dict[str, Any]]


# ---------------------------------------------------------------- loading


def variant_of(label: str) -> str:
    return label.split("=", 1)[-1]


def complexity(variant: str) -> int:
    """Modifier tokens on top of P0 (P0 = 0): the one-SE rule's notion of "simpler"."""
    return sum(1 for t in variant.split("+") if t != "P0")


def load_runs(paths: list[str]) -> tuple[dict[str, dict], dict[str, dict], list[dict]]:
    """(full-dev points, subset points, file log) of one model; a later file wins. Subset
    points are pruned round by round (one subset file = one round, see `prune_rounds`)."""
    full: dict[str, dict] = {}
    sub: dict[str, dict] = {}
    log = []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        target = sub if data.get("subset") else full
        names = []
        for pt in data["points"]:
            v = variant_of(pt["label"])
            rnd = sum(1 for f in log if f["subset"]) + 1 if data.get("subset") else 0
            target[v] = {
                "metrics": pt["metrics"],
                "records": pt["records"],
                "file": p,
                "round": rnd,
            }
            names.append(v)
        log.append({"file": p, "subset": data.get("subset") or 0, "variants": names})
    return full, sub, log


# ---------------------------------------------------------------- statistics


def fold_acc(recs: Recs, fold: dict[str, int], folds: list[int]) -> list[float]:
    return [mean(r["joint_correct"] for c, r in recs.items() if fold[c] == f) for f in folds]


def one_se(
    scores: dict[str, list[float]], cost: dict[str, float], order: list[str]
) -> tuple[str, str]:
    """(chosen, raw best) by the one-SE rule over per-fold scores."""
    means = {v: mean(s) for v, s in scores.items()}
    best = max(order, key=lambda v: (means[v], -order.index(v)))
    s = scores[best]
    se = (stdev(s) / math.sqrt(len(s))) if len(s) > 1 else 0.0
    ok = [v for v in order if means[v] >= means[best] - se - 1e-12]
    chosen = min(ok, key=lambda v: (complexity(v), cost[v], order.index(v)))
    return chosen, best


def nested(
    per_fold: dict[str, list[float]], cost: dict[str, float], order: list[str]
) -> tuple[list[float], list[str]]:
    """Held-out score per outer fold of the one-SE procedure run on the other folds."""
    k = len(next(iter(per_fold.values())))
    held, picks = [], []
    for f in range(k):
        inner = {v: [x for i, x in enumerate(s) if i != f] for v, s in per_fold.items()}
        chosen, _ = one_se(inner, cost, order)
        held.append(per_fold[chosen][f])
        picks.append(chosen)
    return held, picks


def discordant(a: Recs, b: Recs) -> tuple[int, int]:
    """(cases a right & b wrong, a wrong & b right) over the shared cases."""
    shared = a.keys() & b.keys()
    return (
        sum(1 for c in shared if a[c]["joint_correct"] > b[c]["joint_correct"]),
        sum(1 for c in shared if a[c]["joint_correct"] < b[c]["joint_correct"]),
    )


def prune_subset(sub: dict[str, dict]) -> dict[str, dict[str, Any]]:
    """Paired difference to the subset leader on the cases error-free for every variant."""
    if not sub:
        return {}
    ids = set.intersection(*(set(p["records"]) for p in sub.values()))
    clean = sorted(c for c in ids if not any(p["records"][c].get("error") for p in sub.values()))
    acc = {v: mean(p["records"][c]["joint_correct"] for c in clean) for v, p in sub.items()}
    lead = max(sub, key=lambda v: (acc[v], -list(sub).index(v)))
    out = {}
    for v, p in sub.items():
        d = [
            p["records"][c]["joint_correct"] - sub[lead]["records"][c]["joint_correct"]
            for c in clean
        ]
        se = stdev(d) / math.sqrt(len(d)) if len(d) > 1 else 0.0
        out[v] = {
            "n_clean": len(clean),
            "joint": round(acc[v], 4),
            "diff_vs_leader": round(mean(d), 4),
            "se": round(se, 4),
            "pruned": v != "P0" and mean(d) < -se - 1e-12,  # P0 is the reference
            "errors": p["metrics"].get("errors", 0),
        }
    return out


def prune_rounds(sub: dict[str, dict]) -> dict[str, dict[str, Any]]:
    """Pruning as executed: round r compares its variants with every variant of rounds <= r
    (the clean-case set of that moment); a variant keeps the verdict of its own round."""
    out: dict[str, dict[str, Any]] = {}
    for rnd in sorted({p["round"] for p in sub.values()}):
        upto = {v: p for v, p in sub.items() if p["round"] <= rnd}
        for v, res in prune_subset(upto).items():
            if sub[v]["round"] == rnd:
                out[v] = res | {"round": rnd}
    return out


def calibrate(recs: Recs, fold: dict[str, int]) -> dict[str, Any]:
    """Final map per stage (all dev) + cross-fitted ECE raw -> calibrated."""
    maps, ece_raw, ece_cal = {}, {}, {}
    for lv in LEVELS:
        conf_raw, conf_cal, ok_all = [], [], []
        for f in sorted(set(fold.values())):
            xs, ys = pairs([r for c, r in recs.items() if fold[c] != f], lv)
            cal = fit_isotonic(xs, ys) if xs else None
            test = [r for c, r in recs.items() if fold[c] == f and r[f"{lv}_conf"] is not None]
            for r in test:
                conf_raw.append(r[f"{lv}_conf"])
                conf_cal.append(cal(r[f"{lv}_conf"]) if cal else r[f"{lv}_conf"])
                ok_all.append(r[f"{lv}_correct"])
        xs, ys = pairs(list(recs.values()), lv)
        if xs:
            maps[lv] = fit_isotonic(xs, ys).model_dump()
        ece_raw[lv] = round(ece(conf_raw, ok_all), 4)
        ece_cal[lv] = round(ece(conf_cal, ok_all), 4)
    return {"calibration": maps, "ece_raw": ece_raw, "ece_cal": ece_cal}


def economics(m: dict[str, Any]) -> dict[str, float]:
    keys = ("cost_per_1k", "p50_ms", "p95_ms", "prompt_tokens", "static_tokens")
    out = {k: round(float(m[k]), 3) for k in keys}
    out["cache_read_tokens"] = round(float(m["cache_read_tokens"]), 1)
    out["completion_tokens"] = round(float(m["completion_tokens"]), 1)
    out["error_rate"] = round(float(m.get("error_rate", 0.0)), 4)
    return out


# ---------------------------------------------------------------- selection


def select(runs: list[tuple[str, str, list[str]]]) -> dict[str, Any]:
    models: dict[str, Any] = {}
    loaded = {}
    for name, model_id, paths in runs:
        full, sub, log = load_runs(paths)
        if "P0" not in full:
            raise SystemExit(f"{name}: no full-dev P0 point (the reference)")
        loaded[model_id] = (name, full, sub, log)
    any_full = next(iter(loaded.values()))[1]["P0"]["records"]
    fold = folds_of(
        [{"id": c, "category": r["category"]} for c, r in any_full.items()], FOLDS, SEED
    )
    ks = list(range(FOLDS))

    for model_id, (name, full, sub, log) in loaded.items():
        for v, p in full.items():
            if p["records"].keys() != fold.keys():
                raise SystemExit(f"{name} {v}: full-dev point does not cover the same cases")
        order = ["P0"] + [v for v in full if v != "P0"]
        per_fold = {v: fold_acc(full[v]["records"], fold, ks) for v in order}
        cost = {v: full[v]["metrics"]["cost_per_1k"] for v in order}
        chosen, best = one_se(per_fold, cost, order)
        held, picks = nested(per_fold, cost, order)
        p0 = full["P0"]["records"]
        variants = {}
        for v in order:
            m = full[v]["metrics"]
            b, c = discordant(full[v]["records"], p0)
            variants[v] = {
                "cv_joint_mean": round(mean(per_fold[v]), 4),
                "cv_joint_sd": round(pstdev(per_fold[v]), 4),
                "discordant_vs_p0": [b, c],
                "flag_errors_over_2pct": m.get("error_rate", 0.0) > ERROR_LIMIT,
                **economics(m),
            }
        sub_log = prune_rounds(sub)
        for v, s in sub_log.items():
            if v != "P0" and "P0" in sub:
                s["discordant_vs_p0"] = list(discordant(sub[v]["records"], sub["P0"]["records"]))
        models[model_id] = {
            "name": name,
            "per_fold": per_fold,
            "cost": cost,
            "order": order,
            "full": full,
            "tuned": {
                "variant": chosen,
                "raw_best": best,
                "nested_joint_mean": round(mean(held), 4),
                "nested_joint_sd": round(pstdev(held), 4),
                "nested_picks": picks,
            },
            "search": {"files": log, "subset": sub_log, "full_dev": variants},
        }

    # canonical: variants on full dev for every model; per-fold mean over models
    common = [
        v
        for v in next(iter(models.values()))["order"]
        if all(v in m["full"] for m in models.values())
    ]
    mean_fold = {
        v: [mean(m["per_fold"][v][f] for m in models.values()) for f in ks] for v in common
    }
    mean_cost = {v: mean(m["cost"][v] for m in models.values()) for v in common}
    canon, canon_best = one_se(mean_fold, mean_cost, common)
    held, picks = nested(mean_fold, mean_cost, common)
    canonical = {
        "variant": canon,
        "raw_best": canon_best,
        "candidates": {v: round(mean(s), 4) for v, s in mean_fold.items()},
        "nested_mean_joint": round(mean(held), 4),
        "nested_picks": picks,
        "models": [m["name"] for m in models.values()],
    }
    for m in models.values():
        held_m = []
        for f, v in enumerate(picks):
            held_m.append(m["per_fold"][v][f])
        m["canonical_nested"] = (round(mean(held_m), 4), round(pstdev(held_m), 4))
    return {"fold": fold, "models": models, "canonical": canonical}


def track_entry(m: dict[str, Any], variant: str, fold: dict[str, int]) -> dict[str, Any]:
    pt = m["full"][variant]
    cal = calibrate(pt["records"], fold)
    s = m["search"]["full_dev"][variant]
    return {
        "variant": variant,
        "calibration": cal["calibration"],
        "cv_joint_mean": s["cv_joint_mean"],
        "cv_joint_sd": s["cv_joint_sd"],
        "ece_raw": cal["ece_raw"],
        "ece_cal": cal["ece_cal"],
        **{
            k: s[k]
            for k in (
                "cost_per_1k",
                "p50_ms",
                "p95_ms",
                "static_tokens",
                "cache_read_tokens",
                "error_rate",
            )
        },
    }


def build_yaml(sel: dict[str, Any]) -> dict[str, Any]:
    fold, canon = sel["fold"], sel["canonical"]
    out: dict[str, Any] = {
        "generated_by": "scripts/analysis/select_prompts.py",
        "rule": (
            "dev only, 5-fold stratified CV seed 0, ITT; one-SE rule (simplest, then cheapest, "
            "tie -> P0); tuned = per model, canonical = per-fold mean over models"
        ),
        "canonical": canon,
        "models": {},
    }
    for model_id, m in sel["models"].items():
        tuned = track_entry(m, m["tuned"]["variant"], fold)
        tuned.update(
            {
                k: m["tuned"][k]
                for k in ("raw_best", "nested_joint_mean", "nested_joint_sd", "nested_picks")
            }
        )
        can = track_entry(m, canon["variant"], fold)
        can["nested_joint_mean"], can["nested_joint_sd"] = m["canonical_nested"]
        out["models"][model_id] = {
            "name": m["name"],
            "canonical": can,
            "tuned": tuned,
            "search": m["search"],
        }
    return out


def markdown(doc: dict[str, Any]) -> str:
    pct = lambda x: f"{100 * x:.1f}"  # noqa: E731
    lines = [
        "| model | track | variant | nested-CV joint | fixed CV joint | ECE skill raw→cal | "
        "ECE tool raw→cal | $/1k | p50 / p95 ms | static tok | cache-read tok | err % |",
        "|" + "---|" * 12,
    ]
    for m in doc["models"].values():
        for track in ("canonical", "tuned"):
            t = m[track]
            lines.append(
                f"| {m['name']} | {track} | {t['variant']} | {pct(t['nested_joint_mean'])} ± "
                f"{pct(t['nested_joint_sd'])} | "
                f"{pct(t['cv_joint_mean'])} ± {pct(t['cv_joint_sd'])} | "
                f"{t['ece_raw']['skill']:.3f}→{t['ece_cal']['skill']:.3f} | "
                f"{t['ece_raw']['tool']:.3f}→{t['ece_cal']['tool']:.3f} | {t['cost_per_1k']:.2f} | "
                f"{t['p50_ms']:.0f} / {t['p95_ms']:.0f} | {t['static_tokens']:.0f} | "
                f"{t['cache_read_tokens']:.0f} | {100 * t['error_rate']:.1f} |"
            )
    lines += [
        "",
        "### Full-dev variants per model (fixed-point CV joint; discordant vs P0 = (+, −))",
        "",
    ]
    lines.append("| model | variant | CV joint | b+/c− vs P0 | $/1k | p50 ms | out tok | err % |")
    lines.append("|" + "---|" * 8)
    for m in doc["models"].values():
        for v, s in m["search"]["full_dev"].items():
            b, c = s["discordant_vs_p0"]
            lines.append(
                f"| {m['name']} | {v} | {pct(s['cv_joint_mean'])} ± {pct(s['cv_joint_sd'])} | "
                f"{b}/{c} | {s['cost_per_1k']:.2f} | {s['p50_ms']:.0f} | "
                f"{s['completion_tokens']:.0f} | "
                f"{100 * s['error_rate']:.1f} |"
            )
    lines += ["", "### Subset pruning (60 cases, error-free for all variants)", ""]
    lines.append("| model | variant | joint | Δ vs leader | SE | pruned | b+/c− vs P0 | errors |")
    lines.append("|" + "---|" * 8)
    for m in doc["models"].values():
        for v, s in m["search"]["subset"].items():
            d = s.get("discordant_vs_p0", ["-", "-"])
            lines.append(
                f"| {m['name']} | {v} | {pct(s['joint'])} | {pct(s['diff_vs_leader'])} | "
                f"{pct(s['se'])} | {'yes' if s['pruned'] else 'no'} | {d[0]}/{d[1]} | "
                f"{s['errors']} |"
            )
    c = doc["canonical"]
    lines += [
        "",
        f"Canonical over {', '.join(c['models'])}: **{c['variant']}** (raw best {c['raw_best']}); "
        "mean CV joint per candidate: "
        + ", ".join(f"{v} {pct(x)}" for v, x in c["candidates"].items())
        + f"; nested mean {pct(c['nested_mean_joint'])} (picks {', '.join(c['nested_picks'])}).",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--runs", nargs="+", action="append", required=True, metavar="NAME=MODEL FILE")
    ap.add_argument("--out", default="config/prompt_selection.yaml")
    ap.add_argument("--md", help="also write the markdown tables here")
    args = ap.parse_args()
    runs = []
    for spec, *paths in args.runs:
        name, _, model_id = spec.partition("=")
        if not model_id or not paths:
            raise SystemExit(f"bad --runs {spec!r}: expected 'Name=model_id file [file...]'")
        runs.append((name, model_id, paths))
    doc = build_yaml(select(runs))
    header = (
        "# Router prompt selection (docs/prompt-apex.md), dev only. Generated by\n"
        "# scripts/analysis/select_prompts.py; applied by\n"
        "# scripts/analysis/apply_prompt_selection.py.\n"
    )
    text = yaml.safe_dump(
        doc, sort_keys=False, allow_unicode=True, width=100, default_flow_style=None
    )
    Path(args.out).write_text(header + text, encoding="utf-8")
    md = markdown(doc)
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
