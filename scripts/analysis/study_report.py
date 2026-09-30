"""Per-strategy analysis of a RESCORED shadow routing-only run (docs/estudo-resultados.md).

Usage: uv run python scripts/analysis/study_report.py <rescored shadow.jsonl>
           [--single <rescored run.jsonl> ...]

Every entry (isolated strategy, simulated cascade, real single run) is scored by the shared
scorer through `eval.simulate` (an isolated strategy is a one-step `single` pipeline), so the
out-of-scope mapping, wrong-skill and error rules are the same everywhere (review H1, H2, M4):
- accuracy is over the (case_id, rep) keys that are error-free for EVERY entry;
- joint % counts a wrong skill as 0 and a tool stage that cannot be replayed (`n_unavail`) as
  0 too (lower bound); `joint cov.` excludes the latter;
- cost / p50 latency are over the keys whose whole route every entry could simulate;
- 95% CIs: paired cluster bootstrap over case ids (fixed seed, 10k); McNemar vs E5 on joint.
`--single` adds real (non-shadow) runs, e.g. E6 Haiku, whose LLM differs from the shadow LLM.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

from routing_study.eval.rescore import read_rescored
from routing_study.eval.scorers import routing_failure
from routing_study.eval.simulate import simulate_rows
from routing_study.eval.stats import bootstrap_mean, bootstrap_stat, fmt_ci, mcnemar
from routing_study.routers.base import ABSTAIN
from routing_study.settings import (
    PipelineStep,
    RoutingConfig,
    Settings,
    StageConfig,
    load_settings,
)

STRATEGIES = ("regex", "bm25", "embedding", "hybrid", "jev", "llm")
CATEGORIES = ("direto", "parafrase", "ambiguo", "multiturno", "fora_escopo", "adversarial")
CASCADES = (
    "e1_regex",
    "e2_bm25",
    "e3_embedding",
    "e4_jev",
    "e5_llm_sonnet",
    "e7_regex_jev",
    "e8_regex_llm",
    "e9_regex_jev_llm",
)
REFERENCE = "e5_llm_sonnet"


def choice(d: dict[str, Any] | None) -> str:
    return (d or {}).get("choice") or ABSTAIN


def pct(xs: list[float]) -> str:
    return f"{100 * mean(xs):.1f}" if xs else "-"


def ece(pairs: list[tuple[float, float]], bins: int = 10) -> float:
    """Expected calibration error over (confidence, correct) pairs."""
    buckets: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for c, ok in pairs:
        buckets[min(int(max(c, 0.0) * bins), bins - 1)].append((c, ok))
    n = len(pairs)
    return (
        sum(
            len(b) / n * abs(mean(c for c, _ in b) - mean(o for _, o in b))
            for b in buckets.values()
        )
        if n
        else 0.0
    )


def isolated(strategy: str) -> Settings:
    stage = StageConfig(pipeline=[PipelineStep(strategy=strategy)])
    return Settings(
        _env_file=None,
        experiment_id=strategy,
        routing=RoutingConfig(mode="single", skill=stage, tool=stage),
    )


def single_run_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A real (rescored) run in the shape of `simulate_rows` results."""
    out = []
    for r in rows:
        s = r.get("scores") or {}
        out.append(
            {
                "key": (r["case_id"], r["rep"]),
                "case_id": r["case_id"],
                "category": r.get("category"),
                "error": r.get("error"),
                "skill_correct": s.get("skill_correct"),
                "joint_correct": s.get("joint_correct"),
                "tool_unavailable": False,
                "confidence": (r.get("skill") or {}).get("confidence") or 0.0,
                "resolved_by": s.get("resolved_by"),
                "cost_usd": r["cost_usd"]["routing"],
                "latency_ms": r["latency_ms"]["routing"],
            }
        )
    return out


def by_case(rows: list[dict[str, Any]], field: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for x in rows:
        v = x.get(field)
        out[x["case_id"]].append(0.0 if v is None else float(v))
    return out


def entry_stats(
    name: str,
    res: list[dict[str, Any]],
    shared: set[Any],
    costed: set[Any],
    ref: dict[Any, float] | None,
) -> dict[str, Any]:
    rows = [x for x in res if x["key"] in shared]
    cost_rows = [x for x in rows if x["key"] in costed]
    joint = {x["key"]: x["joint_correct"] for x in rows if x.get("joint_correct") is not None}
    cats: dict[str, list[float]] = defaultdict(list)
    for x in rows:
        cats[x["category"]].append(float(x["skill_correct"]))
    return {
        "name": name,
        "n": len(rows),
        "errors": sum(1 for x in res if x["error"]),
        "skill": pct([float(x["skill_correct"]) for x in rows]),
        "joint_ci": bootstrap_mean(by_case(rows, "joint_correct")),
        "joint_cov": pct(list(joint.values())),
        "n_unavail": sum(1 for x in rows if x["tool_unavailable"]),
        "ece": ece([(float(x.get("confidence") or 0), float(x["skill_correct"])) for x in rows]),
        "cost_ci": bootstrap_mean(by_case(cost_rows, "cost_usd")),
        "p50_ci": bootstrap_stat(by_case(cost_rows, "latency_ms"), np.median),
        "mcnemar": mcnemar(joint, ref) if ref is not None and name != REFERENCE else None,
        "resolved_by": dict(Counter(x["resolved_by"] for x in rows)),
        "by_cat": {c: pct(cats[c]) for c in CATEGORIES},
    }


def confusions(rows: list[dict[str, Any]], s: str, top: int = 5) -> list[tuple[str, int]]:
    c: Counter[str] = Counter()
    for r in rows:
        exp = r["expected"]
        sd = r["skill"]["shadow"].get(s)
        if sd is None or routing_failure([sd], sd.get("choice") is not None):
            continue
        sk = choice(sd)
        if sk not in exp["acceptable_skills"]:
            c[f"skill {'/'.join(exp['acceptable_skills'])} -> {sk}"] += 1
        td = (r.get("tool") or {}).get("shadow", {}).get(s)
        if td and sk in exp["acceptable_skills"] and choice(td) not in exp["acceptable_tools"]:
            c[f"tool {'/'.join(exp['acceptable_tools'])} -> {choice(td)}"] += 1
    return c.most_common(top)


def _mc(m: tuple[int, int, int, float] | None) -> str:
    return "-" if m is None else f"{m[1]}/{m[2]} p={m[3]:.3g}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("shadow", type=Path)
    ap.add_argument("--single", type=Path, nargs="*", default=[])
    args = ap.parse_args()
    prov, rows = read_rescored(args.shadow)
    rows = [r for r in rows if (r.get("skill") or {}).get("shadow")]
    entries: dict[str, list[dict[str, Any]]] = {}
    for s in STRATEGIES:
        if any(s in r["skill"]["shadow"] for r in rows):
            entries[s] = simulate_rows(rows, isolated(s))
    for c in CASCADES:
        entries[c] = simulate_rows(rows, load_settings(Path(f"config/experiments/{c}.yaml")))
    for path in args.single:
        srows = read_rescored(path)[1]
        entries[f"{srows[0]['run_name']} (real run)"] = single_run_rows(srows)

    keys = [{x["key"] for x in res if not x["error"]} for res in entries.values()]
    shared = set.intersection(*keys)
    costed = (
        set.intersection(
            *({x["key"] for x in res if x["cost_usd"] is not None} for res in entries.values())
        )
        & shared
    )
    ref_rows = entries.get(REFERENCE) or []
    ref = {
        x["key"]: x["joint_correct"]
        for x in ref_rows
        if x["key"] in shared and x.get("joint_correct") is not None
    }
    stats = [entry_stats(n, res, shared, costed, ref) for n, res in entries.items()]

    print(f"# shadow run {args.shadow.name}: {len(rows)} rows\n")
    print(
        f"scorer {prov['scorer_hash']} | dataset {prov['dataset']['sha256'][:12]} | "
        f"run git {prov['run_git_sha']} | {len(shared)} (case, rep) keys error-free for every "
        f"entry; cost/latency over {len(costed)} keys every entry fully simulated\n"
    )
    print(
        "| entry | n | err | skill % | joint % 95% CI | joint cov. % | n_unavail | ECE "
        "| US$/1k routing 95% CI | p50 ms 95% CI | McNemar joint vs E5 (entry/E5 only) "
        "| resolved_by |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in stats:
        print(
            f"| {s['name']} | {s['n']} | {s['errors']} | {s['skill']} | {fmt_ci(s['joint_ci'])} "
            f"| {s['joint_cov']} | {s['n_unavail']} | {s['ece']:.3f} "
            f"| {fmt_ci(s['cost_ci'], scale=1000.0, digits=4)} "
            f"| {fmt_ci(s['p50_ci'], scale=1.0, digits=0)} | {_mc(s['mcnemar'])} "
            f"| {s['resolved_by']} |"
        )
    print("\n## skill accuracy by category\n")
    print("| entry | " + " | ".join(CATEGORIES) + " |")
    print("|---|" + "---|" * len(CATEGORIES))
    for s in stats:
        print(f"| {s['name']} | " + " | ".join(s["by_cat"][c] for c in CATEGORIES) + " |")
    print("\n## top errors per strategy\n")
    for s in STRATEGIES:
        print(f"- **{s}**: " + "; ".join(f"{k} ({v})" for k, v in confusions(rows, s)))


if __name__ == "__main__":
    main()
