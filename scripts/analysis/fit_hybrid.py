"""Fit the hybrid LOGISTIC STACKER (and evaluate the learned cascade deferral scorer) on DEV.

Usage:
  uv run python scripts/analysis/fit_hybrid.py config/experiments/e11_hybrid.yaml \\
      [--members regex,bm25,embedding] [--l2 0.1,1,10] [--folds 5] [--seed 0] \\
      [--summary results/phase2/hybrid_stacker.json]

1. Every member router (with its configured calibration) routes every dev case: the skill
   stage over the skill options, the tool stage over the tools of the GOLD skill (training
   only; evaluation below uses the real pipeline). Per option: `stack_features` + label
   "this option would be scored correct".
2. Nested CV (stratified 5-fold, seed 0, same folds as tune_router.py): per outer fold, the L2
   strength is picked by inner leave-one-fold-out top-1 accuracy on the train folds, the
   stacker is fitted on the train folds and the hybrid pipeline (fusion=stacker) is scored on
   the held-out fold with tune_router's `evaluate` (same scorer as `study run`).
3. The final stacker (all dev, the most picked L2) is printed as a config block.
4. Deferral: CV AUROC/Brier of `fit_deferral` (P(member[0] correct) from the members'
   confidences, margins and agreement) vs member[0]'s calibrated confidence alone, at the skill
   stage — the learned deferral scorer a cascade can use instead of a single-confidence gate.
Only catalog text and dev labels are used; the test split is never read.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tune_router import (  # noqa: E402
    LEVELS,
    METRICS,
    _input,
    acc,
    dev_catalog,
    evaluate,
    folds_of,
    load_dev,
    pairs,
    patched,
)

from routing_study.eval.scorers import ESCALATE, skill_can_be_correct  # noqa: E402
from routing_study.routers.base import ABSTAIN, GLOBAL_OPTION  # noqa: E402
from routing_study.routers.calibration import brier, ece, fit_logistic  # noqa: E402
from routing_study.routers.hybrid import (  # noqa: E402
    deferral_features,
    fit_deferral,
    stack_feature_names,
    stack_features,
)
from routing_study.routers.pipeline import build_routers  # noqa: E402
from routing_study.settings import load_settings  # noqa: E402


def gold_skill(expected: dict[str, Any]) -> str:
    real = [s for s in expected["acceptable_skills"] if s != ABSTAIN]
    return real[0] if real else GLOBAL_OPTION


def tool_ok(tool: str, expected: dict[str, Any]) -> bool:
    return tool in expected["acceptable_tools"] or (
        tool == ESCALATE and ABSTAIN in expected["acceptable_tools"]
    )


async def member_decisions(settings: Any, rows: list[dict[str, Any]], catalog: Any, members):
    routers = build_routers(settings, set(members))
    out: dict[str, dict[str, Any]] = {}
    for case in rows:
        rec: dict[str, Any] = {}
        for lv in LEVELS:
            skill = gold_skill(case["expected"]) if lv == "tool" else None
            opts = catalog.skill_options() if lv == "skill" else catalog.tool_options(skill)
            inp = _input(case, lv, skill)
            decs = {m: await routers[m]._route(inp, opts) for m in members}
            ids = [o.id for o in opts]
            ok = {
                o: (
                    skill_can_be_correct(o, case["expected"])
                    if lv == "skill"
                    else tool_ok(o, case["expected"])
                )
                for o in ids
            }
            rec[lv] = {"feats": stack_features(decs, ids), "ok": ok, "decs": decs}
        out[case["id"]] = rec
    return out


def stage_rows(data: dict[str, Any], ids: list[str], lv: str):
    xs, ys = [], []
    for cid in ids:
        st = data[cid][lv]
        for o, f in st["feats"].items():
            xs.append(f)
            ys.append(float(st["ok"][o]))
    return xs, ys


def top1(data: dict[str, Any], ids: list[str], lv: str, model: Any) -> float:
    hits = []
    for cid in ids:
        st = data[cid][lv]
        best = max(st["feats"], key=lambda o: model(st["feats"][o]))
        hits.append(float(st["ok"][best]))
    return mean(hits) if hits else 0.0


def auroc(scores: list[float], labels: list[float]) -> float:
    pos = [s for s, y in zip(scores, labels, strict=True) if y]
    neg = [s for s, y in zip(scores, labels, strict=True) if not y]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("config")
    ap.add_argument("--members", default="")
    ap.add_argument("--l2", default="0.1,1,10")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--summary")
    args = ap.parse_args()

    base = load_settings(args.config)
    members = args.members.split(",") if args.members else list(base.strategies.hybrid.members)
    if args.members:
        base = patched(base, [(["strategies", "hybrid", "members"], members)])
    names = stack_feature_names(members)
    l2s = [float(v) for v in args.l2.split(",")]
    rows = load_dev()
    fold = folds_of(rows, args.folds, args.seed)
    catalog = asyncio.run(dev_catalog(base))
    data = asyncio.run(member_decisions(base, rows, catalog, members))
    by_id = {r["id"]: r for r in rows}

    per_fold: dict[str, list[float]] = {m: [] for m in METRICS}
    held: list[dict[str, Any]] = []
    picked: list[float] = []
    for f in range(args.folds):
        train = [c for c, fo in fold.items() if fo != f]
        test = [c for c, fo in fold.items() if fo == f]
        models = {}
        for lv in LEVELS:
            inner = []
            for l2 in l2s:
                scores = []
                for g in range(args.folds):
                    if g == f:
                        continue
                    tr = [c for c in train if fold[c] != g]
                    va = [c for c in train if fold[c] == g]
                    m = fit_logistic(*stage_rows(data, tr, lv), names, l2=l2)
                    scores.append(top1(data, va, lv, m))
                inner.append((mean(scores), -l2, l2))  # ties -> stronger regularisation
            l2 = max(inner)[2]
            picked.append(l2)
            models[lv] = fit_logistic(*stage_rows(data, train, lv), names, l2=l2)
        s = patched(
            base,
            [
                (["strategies", "hybrid", "fusion"], "stacker"),
                (
                    ["strategies", "hybrid", "stacker"],
                    {lv: m.model_dump() for lv, m in models.items()},
                ),
                (["strategies", "hybrid", "calibration"], {}),
            ],
        )
        recs = asyncio.run(evaluate(s, [by_id[c] for c in test], catalog, args.concurrency))
        for m in METRICS:
            per_fold[m].append(acc(list(recs.values()), m))
        held.extend(recs.values())

    print(f"# {args.config} members={members} dev n={len(rows)} folds={args.folds}")
    print("## stacker, nested CV (held-out; mean ± std over folds)")
    for m in METRICS:
        print(f"{m:14s} {100 * mean(per_fold[m]):5.1f} ± {100 * pstdev(per_fold[m]):4.1f}")
    cal_stats = {}
    for lv in LEVELS:
        conf, ok = pairs(held, lv)
        cal_stats[lv] = {"n": len(conf), "ece": ece(conf, ok), "brier": brier(conf, ok)}
        print(f"{lv:5s} n={len(conf)} ECE={ece(conf, ok):.3f} Brier={brier(conf, ok):.4f}")
    final_l2 = Counter(picked).most_common(1)[0][0]
    final = {
        lv: fit_logistic(*stage_rows(data, list(fold), lv), names, l2=final_l2).model_dump()
        for lv in LEVELS
    }
    print(f"\n## final stacker (all dev, l2={final_l2}; picks {dict(Counter(picked))})")
    print(yaml.safe_dump({"stacker": final}, default_flow_style=None, sort_keys=False))

    # ---- learned deferral scorer vs single confidence (skill stage, member[0] decisions)
    lead = members[0]
    cases = [c for c in fold if data[c]["skill"]["decs"][lead].choice is not None]
    feats = {
        c: deferral_features(data[c]["skill"]["decs"], turns=len(by_id[c]["turns"])) for c in cases
    }
    label = {c: float(data[c]["skill"]["ok"][data[c]["skill"]["decs"][lead].choice]) for c in cases}
    learned, single, ys = [], [], []
    for f in range(args.folds):
        tr = [c for c in cases if fold[c] != f]
        te = [c for c in cases if fold[c] == f]
        if not te:
            continue
        m = fit_deferral([feats[c] for c in tr], [label[c] for c in tr])
        learned += [m(feats[c]) for c in te]
        single += [float(data[c]["skill"]["decs"][lead].confidence) for c in te]
        ys += [label[c] for c in te]
    deferral = {
        "lead": lead,
        "n": len(ys),
        "auroc_learned": auroc(learned, ys),
        "auroc_single": auroc(single, ys),
        "brier_learned": brier(learned, ys),
        "brier_single": brier(single, ys),
    }
    print(f"## deferral (skill stage, P({lead} correct), CV held-out): {json.dumps(deferral)}")

    if args.summary:
        out = {
            "config": args.config,
            "members": members,
            "nested": {m: {"mean": mean(v), "std": pstdev(v)} for m, v in per_fold.items()},
            "calibration_stats": cal_stats,
            "l2_picks": dict(Counter(picked)),
            "final_l2": final_l2,
            "stacker": final,
            "deferral": deferral,
            "p50_ms": float(np.median([r["skill_u"]["ms"] + r["tool_u"]["ms"] for r in held])),
        }
        Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary).write_text(json.dumps(out, indent=1, default=float), "utf-8")


if __name__ == "__main__":
    sys.exit(main())
