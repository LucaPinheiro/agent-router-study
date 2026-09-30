"""Tune a routing config on the DEV split with stratified k-fold cross-validation.

Usage:
  uv run python scripts/analysis/tune_router.py config/experiments/e2_bm25.yaml \\
      [--set strategies.bm25.k1=1.2] [--grid strategies.bm25.b=0.3,0.5,0.75] \\
      [--folds 5] [--seed 0] [--calibrate] [--errors]
  uv run python scripts/analysis/tune_router.py config/experiments/e6b_llm_qwen3_local.yaml \
      --prompt-variant P0,P0+P1,P0+P6c --subset 60 --concurrency 1 --preload \
      --out results/prompt_apex/e6b_round1.json

`--prompt-variant` is sugar for `--grid strategies.<router>.prompt_variant=...` (the router of
the skill pipeline's first step, or `--strategy`). `--subset N` scores a stratified, seeded
N-case subset of dev (early pruning); the full dev pass reuses its cached decisions. Per grid
point the report adds the context economics of the routing calls: CV joint mean ± std of the
FIXED point over the folds, raw ECE per level, prompt tokens split into static prefix and
dynamic part (estimated from the rendered characters), cache read/write tokens, output
tokens, cost per 1k cases (skill + tool call, original cost even when served from cache) and
case latency p50/p95. `--out` writes all of it (plus per-case records) as JSON after each
point, so an interrupted search keeps what it paid for.

Runs the config's skill + tool pipelines exactly like `study run --mode routing-only` (same
`RoutingPipeline`, same shared scorer `routing_scores`) over data/dataset_dev.jsonl. The
catalog comes from the in-process MCP server (no network); regex/BM25 make no paid call, and a
paid strategy (embedding, llm, jev, hybrid) reuses its response cache, so a grid over
pipeline-only parameters costs one pass.

Protocol (nested, so the reported number is an estimate of the TUNING PROCEDURE, not of the
best grid point on the data that chose it):
- every grid point is scored on every dev case (routers have no data-fitted state);
- per fold: pick the grid point with the best mean joint accuracy on the other k-1 folds
  (ties -> first in grid order), score it on the held-out fold;
- `--calibrate`: per fold, fit an isotonic map raw confidence -> P(correct) per level on the
  train folds and apply it to the held-out fold (ECE before/after, precision at thresholds);
  finally the best grid point and maps are refit on all of dev and printed as config YAML.
The test split is never read.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

import yaml
from fastmcp import Client

from routing_study.budget import BudgetExceededError
from routing_study.catalog import Catalog, fetch_catalog
from routing_study.eval.scorers import routing_scores
from routing_study.routers.base import GLOBAL_OPTION, Message, RoutingInput
from routing_study.routers.calibration import Calibration, ece, fit_isotonic
from routing_study.routers.pipeline import build_pipeline, build_routers
from routing_study.settings import (
    RoutingConfig,
    Settings,
    StrategiesConfig,
    _set_path,
    load_settings,
)

DEV = Path("data/dataset_dev.jsonl")  # the only split this script reads
CATEGORIES = ("direto", "parafrase", "ambiguo", "multiturno", "fora_escopo", "adversarial")
METRICS = ("skill_correct", "tool_correct", "joint_correct")
LEVELS = ("skill", "tool")
THRESHOLDS = (0.5, 0.7, 0.8, 0.9)
ERROR_RETRIES = 3


# ---------------------------------------------------------------- data / config


def load_dev() -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in DEV.read_text(encoding="utf-8").splitlines() if ln.strip()]


def folds_of(rows: list[dict[str, Any]], k: int, seed: int) -> dict[str, int]:
    """case id -> fold, stratified by category, seeded."""
    rng = random.Random(seed)
    out: dict[str, int] = {}
    by_cat: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r["id"])
    offset = 0
    for cat in sorted(by_cat):
        ids = sorted(by_cat[cat])
        rng.shuffle(ids)
        for i, cid in enumerate(ids):
            out[cid] = (offset + i) % k
        offset += len(ids)  # spreads category remainders over different folds
    return out


def subset_of(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """Stratified (by category, proportional, largest remainders), seeded n-case subset."""
    if n >= len(rows):
        return rows
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    quota = {c: n * len(v) / len(rows) for c, v in by_cat.items()}
    take = {c: int(q) for c, q in quota.items()}
    for c in sorted(quota, key=lambda c: (-(quota[c] - take[c]), c))[: n - sum(take.values())]:
        take[c] += 1
    rng = random.Random(seed)
    keep: set[str] = set()
    for cat in sorted(by_cat):
        ids = sorted(r["id"] for r in by_cat[cat])
        rng.shuffle(ids)
        keep.update(ids[: take[cat]])
    return [r for r in rows if r["id"] in keep]


def parse_assign(raw: str) -> tuple[list[str], list[Any]]:
    """`a.b.c=v1,v2` -> (path, [values]); values are YAML scalars (a `[..]` list stays one)."""
    key, _, vals = raw.partition("=")
    if not key or not vals:
        raise SystemExit(f"bad assignment {raw!r}: expected key.path=value[,value...]")
    parts = [vals] if vals.lstrip().startswith(("[", "{")) else vals.split(",")
    return key.strip().split("."), [yaml.safe_load(v) for v in parts]


def patched(settings: Settings, assigns: list[tuple[list[str], Any]]) -> Settings:
    data = settings.model_dump(mode="json", include={"routing", "strategies"})
    for path, value in assigns:
        if path[0] not in data:
            raise SystemExit(f"only routing.* / strategies.* can be set (got {'.'.join(path)})")
        _set_path(data, path, value)
    return settings.model_copy(
        update={
            "routing": RoutingConfig.model_validate(data["routing"]),
            "strategies": StrategiesConfig.model_validate(data["strategies"]),
        }
    )


async def dev_catalog(settings: Settings) -> Catalog:
    from mcp_server.server import mcp

    return await fetch_catalog(settings, Client(mcp))


# ---------------------------------------------------------------- evaluation


def _input(case: dict[str, Any], level: str, skill: str | None = None) -> RoutingInput:
    turns = case["turns"]
    return RoutingInput(
        message=turns[-1]["content"],
        level=level,  # type: ignore[arg-type]
        loaded_skill=skill,
        history=[Message(role=t["role"], content=t["content"]) for t in turns[:-1]],
    )


def _raw(decision: Any) -> float:
    return float(decision.usage.get("raw_confidence", decision.confidence))


def call_usage(steps: list[Any]) -> dict[str, Any]:
    """Context economics of the consulted routing calls of one stage. Static/dynamic tokens
    split the provider's prompt tokens by the rendered characters of the system prefix vs
    the user message (an estimate; providers report one prompt total)."""
    out: dict[str, Any] = dict.fromkeys(
        ("cost", "ms", "prompt", "completion", "cache_read", "cache_write", "static", "dynamic"),
        0.0,
    )
    out["parse_fail"] = False
    out["error"] = False
    for d in steps:
        u = d.usage
        prompt = float(u.get("prompt_tokens") or 0)
        sc, dc = float(u.get("static_chars") or 0), float(u.get("dynamic_chars") or 0)
        share = sc / (sc + dc) if sc + dc else 0.0
        out["cost"] += d.cost_usd
        out["ms"] += d.latency_ms
        out["prompt"] += prompt
        out["completion"] += float(u.get("completion_tokens") or 0)
        out["cache_read"] += float(u.get("cache_read") or 0)
        out["cache_write"] += float(u.get("cache_write") or 0)
        out["static"] += prompt * share
        out["dynamic"] += prompt * (1 - share)
        out["parse_fail"] |= bool(u.get("parse_fail"))
        out["error"] |= bool(u.get("error"))
    return out


async def evaluate(
    settings: Settings, rows: list[dict[str, Any]], catalog: Catalog, concurrency: int = 4
) -> dict[str, dict[str, Any]]:
    """case id -> {category, scores, per-level (choice, raw confidence)} for one config."""
    stages = (settings.routing.skill, settings.routing.tool)
    wanted = {s.strategy for st in stages for s in st.pipeline}
    routers = build_routers(settings, wanted)
    skill_p, tool_p = (build_pipeline(settings, lv, routers) for lv in LEVELS)  # type: ignore[arg-type]
    sem = asyncio.Semaphore(concurrency)

    async def run(pipe: Any, inp: RoutingInput, options: list[Any]) -> Any:
        """A routing error (throttling, timeout: infrastructure, excluded from accuracy by
        `study run`) is retried; failures are never cached, so only they are re-sent. A
        parse failure is the router's own answer and is scored."""
        for attempt in range(ERROR_RETRIES + 1):
            res = await pipe.run(inp, options)
            if not res.routing_error or attempt == ERROR_RETRIES:
                return res
            await asyncio.sleep(5 * (attempt + 1))
        return res

    async def one(case: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        async with sem:
            sk = await run(skill_p, _input(case, "skill"), catalog.skill_options())
            skill = sk.decision.choice
            rec: dict[str, Any] = {
                "category": case["category"],
                "message": case["turns"][-1]["content"],
                "expected": case["expected"],
                "skill": skill,
                "skill_conf": _raw(sk.decision) if skill else None,
                "tool": None,
                "tool_conf": None,
                "skill_u": call_usage(sk.steps),
                "tool_u": call_usage([]),
            }
            if skill is not None:
                inp = _input(case, "tool", None if skill == GLOBAL_OPTION else skill)
                tl = await run(tool_p, inp, catalog.tool_options(skill))
                rec["tool"] = tl.decision.choice
                rec["tool_conf"] = _raw(tl.decision) if tl.decision.choice else None
                rec["tool_u"] = call_usage(tl.steps)
            return case["id"], rec | routing_scores(skill, rec["tool"], case["expected"])

    return dict(await asyncio.gather(*(one(c) for c in rows)))


def acc(recs: list[dict[str, Any]], metric: str) -> float:
    return mean(r[metric] for r in recs) if recs else float("nan")


def pairs(recs: list[dict[str, Any]], level: str) -> tuple[list[float], list[float]]:
    """(raw confidence, correct) of the decisions a level actually made (abstentions out)."""
    got = [r for r in recs if r[f"{level}_conf"] is not None]
    return [r[f"{level}_conf"] for r in got], [r[f"{level}_correct"] for r in got]


def pct(xs: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100); nan for no data."""
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, round(q / 100 * len(xs) + 0.5) - 1))]


def point_metrics(
    recs: dict[str, dict[str, Any]], fold: dict[str, int], folds: int
) -> dict[str, Any]:
    """One FIXED grid point: accuracy per fold (mean ± std), raw ECE per level and the
    context economics of its routing calls (per call means, per case cost and latency)."""
    rows = list(recs.values())
    per_fold = {
        m: [
            acc(fr, m) for f in range(folds) if (fr := [r for c, r in recs.items() if fold[c] == f])
        ]
        for m in METRICS
    }
    calls = [r[f"{lv}_u"] for r in rows for lv in LEVELS if r[f"{lv}_u"]["prompt"]]
    case_ms = [r["skill_u"]["ms"] + r["tool_u"]["ms"] for r in rows]
    out: dict[str, Any] = {
        "n": len(rows),
        **{f"{m}_mean": mean(v) for m, v in per_fold.items()},
        **{f"{m}_std": pstdev(v) for m, v in per_fold.items()},
        **{f"{m}_all": acc(rows, m) for m in METRICS},
        "cost_per_1k": 1000 * mean(r["skill_u"]["cost"] + r["tool_u"]["cost"] for r in rows),
        "p50_ms": median(case_ms),
        "p95_ms": pct(case_ms, 95),
        "tool_p50_ms": median([r["tool_u"]["ms"] for r in rows if r["tool_u"]["ms"]] or [0.0]),
        "parse_fail": sum(r[f"{lv}_u"]["parse_fail"] for r in rows for lv in LEVELS),
        "errors": sum(r[f"{lv}_u"].get("error", False) for r in rows for lv in LEVELS),
    }
    for key in ("prompt", "static", "dynamic", "cache_read", "cache_write", "completion"):
        out[f"{key}_tokens"] = mean(c[key] for c in calls) if calls else 0.0
    for lv in LEVELS:
        conf, ok = pairs(rows, lv)
        out[f"ece_{lv}"] = ece(conf, ok) if conf else float("nan")
    return out


def selection_key(m: dict[str, Any]) -> tuple[float, float, float]:
    """Best joint accuracy; ties -> lower cost, then lower latency (docs/prompt-apex.md)."""
    return (m["joint_correct_mean"], -m["cost_per_1k"], -m["p50_ms"])


# ---------------------------------------------------------------- report


def fmt(xs: list[float]) -> str:
    return f"{100 * mean(xs):5.1f} ± {100 * pstdev(xs):4.1f}"


def label(assign: tuple[tuple[str, Any], ...]) -> str:
    return " ".join(f"{k}={v}" for k, v in assign) or "(config as is)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("config")
    ap.add_argument("--set", action="append", default=[], help="fixed override key.path=value")
    ap.add_argument("--grid", action="append", default=[], help="key.path=v1,v2,... (cartesian)")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--calibrate", action="store_true", help="fit isotonic maps on train folds")
    ap.add_argument("--errors", action="store_true", help="print wrong cases of the best point")
    ap.add_argument("--top", type=int, default=10, help="grid points shown in the full-dev table")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--prompt-variant", help="v1,v2 = --grid strategies.<router>.prompt_variant")
    ap.add_argument("--strategy", help="router of --prompt-variant (default: skill pipeline[0])")
    ap.add_argument("--subset", type=int, default=0, help="stratified n-case dev subset")
    ap.add_argument("--preload", action="store_true", help="load the local models first")
    ap.add_argument("--out", help="write per-point metrics + records as JSON")
    args = ap.parse_args()

    base = load_settings(args.config)
    fixed = [(p, v[0]) for p, v in map(parse_assign, args.set)]
    if args.prompt_variant:
        router = args.strategy or base.routing.skill.pipeline[0].strategy
        args.grid.append(f"strategies.{router}.prompt_variant={args.prompt_variant}")
    grid_axes = [(".".join(p), vs) for p, vs in map(parse_assign, args.grid)]
    points = [
        tuple(zip([k for k, _ in grid_axes], combo, strict=True))
        for combo in itertools.product(*(vs for _, vs in grid_axes))
    ]
    rows = load_dev()
    if args.subset:
        rows = subset_of(rows, args.subset, args.seed)
    fold = folds_of(rows, args.folds, args.seed)
    catalog = asyncio.run(dev_catalog(base))
    if args.preload:
        from routing_study.llm import preload_ollama

        stages = (base.routing.skill, base.routing.tool)
        wanted = {st.strategy for stg in stages for st in stg.pipeline}
        print("# preloaded:", asyncio.run(preload_ollama(base, wanted)))

    results: list[dict[str, dict[str, Any]]] = []
    metrics: list[dict[str, Any]] = []
    for pt in points:
        s = patched(base, fixed + [(k.split("."), v) for k, v in pt])
        try:
            results.append(asyncio.run(evaluate(s, rows, catalog, args.concurrency)))
        except BudgetExceededError as exc:
            print(f"# BUDGET GUARD at {label(pt)}: {exc}; stopping the grid", file=sys.stderr)
            points = points[: len(results)]
            break
        metrics.append(point_metrics(results[-1], fold, args.folds))
        print(f"# done {label(pt)}: {json.dumps(metrics[-1], default=float)}", flush=True)
        if args.out:
            write_out(args, points, results, metrics)
    if not results:
        return

    # ---- full-dev table per grid point (optimistic: chosen on the same data)
    # best first: joint accuracy, then lower cost, then lower latency (stable: grid order)
    order = sorted(range(len(points)), key=lambda i: selection_key(metrics[i]), reverse=True)
    print(f"# {args.config}  dev n={len(rows)}  folds={args.folds} seed={args.seed}")
    if fixed:
        print("# fixed:", " ".join(f"{'.'.join(p)}={v}" for p, v in fixed))
    if len(points) > 1:
        print(f"\n## full dev per grid point (top {args.top} of {len(points)}; optimistic)")
        print(f"{'skill':>6} {'tool':>6} {'joint':>6}  point")
        for i in order[: args.top]:
            recs = list(results[i].values())
            print(" ".join(f"{100 * acc(recs, m):6.1f}" for m in METRICS) + f"  {label(points[i])}")

    print(f"\n## per point ({args.folds}-fold CV of the fixed point; economics per call / case)")
    print(
        f"{'joint':>13} {'skill':>6} {'tool':>6} {'ECEs':>5} {'ECEt':>5} {'prompt':>6} "
        f"{'static':>6} {'dyn':>5} {'c.rd':>5} {'c.wr':>5} {'out':>5} {'$/1k':>7} "
        f"{'p50':>6} {'p95':>6} {'tl50':>6} {'pf':>3}  point"
    )
    for i in sorted(range(len(points)), key=lambda i: selection_key(metrics[i]), reverse=True):
        m = metrics[i]
        print(
            f"{100 * m['joint_correct_mean']:5.1f} ± {100 * m['joint_correct_std']:4.1f} "
            f"{100 * m['skill_correct_all']:6.1f} {100 * m['tool_correct_all']:6.1f} "
            f"{m['ece_skill']:5.3f} {m['ece_tool']:5.3f} {m['prompt_tokens']:6.0f} "
            f"{m['static_tokens']:6.0f} {m['dynamic_tokens']:5.0f} {m['cache_read_tokens']:5.0f} "
            f"{m['cache_write_tokens']:5.0f} {m['completion_tokens']:5.0f} "
            f"{m['cost_per_1k']:7.3f} {m['p50_ms']:6.0f} {m['p95_ms']:6.0f} "
            f"{m['tool_p50_ms']:6.0f} {m['parse_fail']:3d}  {label(points[i])}"
        )

    # ---- nested CV
    per_fold: dict[str, list[float]] = defaultdict(list)
    held: list[dict[str, Any]] = []  # pooled held-out records (with calibrated confidences)
    chosen: list[int] = []
    for f in range(args.folds):
        train_ids = [cid for cid, fo in fold.items() if fo != f]
        test_ids = [cid for cid, fo in fold.items() if fo == f]
        if not test_ids:  # tiny --subset: fewer cases than folds
            continue
        best = max(
            range(len(points)),
            key=lambda i: (
                acc([results[i][c] for c in train_ids], "joint_correct"),
                -metrics[i]["cost_per_1k"],
                -metrics[i]["p50_ms"],
                -i,
            ),
        )
        chosen.append(best)
        test = [dict(results[best][c]) for c in test_ids]
        for m in METRICS:
            per_fold[m].append(acc(test, m))
        if args.calibrate:
            train = [results[best][c] for c in train_ids]
            for lv in LEVELS:
                xs, ys = pairs(train, lv)
                cal = fit_isotonic(xs, ys) if xs else None
                for r in test:
                    if r[f"{lv}_conf"] is not None:
                        r[f"{lv}_cal"] = cal(r[f"{lv}_conf"]) if cal else r[f"{lv}_conf"]
        held.extend(test)

    print(f"\n## {args.folds}-fold CV (held-out; mean ± std over folds)")
    for m in METRICS:
        print(f"{m:14s} {fmt(per_fold[m])}")
    picks = defaultdict(int)
    for i in chosen:
        picks[label(points[i])] += 1
    print("selected per fold:", "; ".join(f"{k} x{v}" for k, v in picks.items()))

    print("\n## per category (pooled held-out, %)")
    print(f"{'category':12s} {'n':>3} {'skill':>6} {'tool':>6} {'joint':>6}")
    for cat in CATEGORIES:
        recs = [r for r in held if r["category"] == cat]
        if recs:
            print(
                f"{cat:12s} {len(recs):3d} "
                + " ".join(f"{100 * acc(recs, m):6.1f}" for m in METRICS)
            )

    print("\n## calibration (pooled held-out; decisions made, abstentions excluded)")
    for lv in LEVELS:
        conf, ok = pairs(held, lv)
        accuracy = 100 * mean(ok) if ok else 0.0
        line = f"{lv:5s} n={len(conf):3d} acc={accuracy:5.1f}  ECE raw={ece(conf, ok):.3f}"
        if args.calibrate:
            got = [r for r in held if r.get(f"{lv}_cal") is not None]
            cal_conf = [r[f"{lv}_cal"] for r in got]
            cal_ok = [r[f"{lv}_correct"] for r in got]
            line += f"  calibrated={ece(cal_conf, cal_ok):.3f}"
            prec = []
            for t in THRESHOLDS:
                sel = [o for c, o in zip(cal_conf, cal_ok, strict=True) if c >= t]
                prec.append(
                    f">={t}: cov {100 * len(sel) / len(cal_ok):.0f}% prec "
                    + (f"{100 * mean(sel):.0f}%" if sel else "-")
                )
            line += "\n      " + " | ".join(prec)
        print(line)

    # ---- final refit on all dev
    best = order[0]
    all_recs = list(results[best].values())
    print(f"\n## final (all dev): {label(points[best])}")
    if args.calibrate:
        cal_cfg: dict[str, dict[str, list[float]]] = {}
        for lv in LEVELS:
            xs, ys = pairs(all_recs, lv)
            if xs:
                c: Calibration = fit_isotonic(xs, ys)
                cal_cfg[lv] = c.model_dump()
        print(yaml.safe_dump({"calibration": cal_cfg}, default_flow_style=None, sort_keys=False))
    if args.errors:
        print("## wrong joint (all dev, best point)")
        for cid, r in sorted(results[best].items(), key=lambda kv: kv[1]["category"]):
            if not r["joint_correct"]:
                exp = r["expected"]
                print(
                    f"- [{r['category']}] {cid}: {r['message']!r}\n"
                    f"    skill {r['skill']} (conf {r['skill_conf']})"
                    f" want {exp['acceptable_skills']}\n"
                    f"    tool  {r['tool']} (conf {r['tool_conf']}) want {exp['acceptable_tools']}"
                )


def write_out(
    args: argparse.Namespace,
    points: list[tuple[tuple[str, Any], ...]],
    results: list[dict[str, dict[str, Any]]],
    metrics: list[dict[str, Any]],
) -> None:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "config": args.config,
        "subset": args.subset,
        "folds": args.folds,
        "seed": args.seed,
        "fixed": args.set,
        "points": [
            {"point": dict(pt), "label": label(pt), "metrics": m, "records": r}
            for pt, m, r in zip(points, metrics, results, strict=False)
        ],
    }
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=float), "utf-8")


if __name__ == "__main__":
    sys.exit(main())
