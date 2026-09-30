"""Per-strategy analysis of a RESCORED shadow routing-only run (docs/estudo-resultados.md).

Usage: uv run python scripts/analysis/study_report.py <rescored shadow.jsonl>
           [--single <rescored run.jsonl> ...]

Every entry (isolated strategy, simulated cascade, real single run) is scored by the shared
scorer through `eval.simulate` (an isolated strategy is a one-step `single` pipeline), so the
out-of-scope mapping, wrong-skill and error rules are the same everywhere (review H1, H2, M4):
- intention to treat (F2): accuracy is over the (case_id, rep) keys every entry has, and an
  error row (a failed routing stage: error or parse failure) counts as WRONG; `err %` is its
  own column; the keys error-free for EVERY entry give a labelled sensitivity column only;
- joint % counts a wrong skill as 0 and a tool stage that cannot be replayed (`n_unavail`) as
  0 too (lower bound); `joint cov.` excludes the latter and the error rows;
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
        s = {} if r.get("error") else r.get("scores") or {}  # an error row is wrong (ITT)
        out.append(
            {
                "key": (r["case_id"], r["rep"]),
                "case_id": r["case_id"],
                "category": r.get("category"),
                "error": r.get("error"),
                "skill_correct": s.get("skill_correct", 0.0),
                "joint_correct": s.get("joint_correct", 0.0),
                "tool_unavailable": False,
                "confidence": (r.get("skill") or {}).get("confidence") or 0.0,
                "resolved_by": s.get("resolved_by"),
                "cost_usd": r["cost_usd"]["routing"],
                "latency_ms": r["latency_ms"]["routing"],
            }
        )
    return out


def by_case(rows: list[dict[str, Any]], field: str) -> dict[str, list[float]]:
    """case id -> values; an error row or a missing value is 0 (ITT)."""
    out: dict[str, list[float]] = defaultdict(list)
    for x in rows:
        v = x.get(field)
        out[x["case_id"]].append(0.0 if x.get("error") or v is None else float(v))
    return out


def entry_stats(
    name: str,
    res: list[dict[str, Any]],
    keys: set[Any],
    error_free: set[Any],
    costed: set[Any],
    ref: dict[Any, float] | None,
) -> dict[str, Any]:
    """ITT over `keys` (an error row is wrong); `error_free` keys give the sensitivity CI."""
    rows = [x for x in res if x["key"] in keys]
    ok = [x for x in rows if not x["error"]]
    cost_rows = [x for x in rows if x["key"] in costed]
    joint = {x["key"]: 0.0 if x["error"] else x.get("joint_correct") or 0.0 for x in rows}
    cats: dict[str, list[float]] = defaultdict(list)
    for x in rows:
        cats[x["category"]].append(0.0 if x["error"] else float(x.get("skill_correct") or 0.0))
    return {
        "name": name,
        "n": len(rows),
        "errors": len(rows) - len(ok),
        "err_pct": pct([float(bool(x["error"])) for x in rows]),
        "skill": pct([0.0 if x["error"] else float(x.get("skill_correct") or 0.0) for x in rows]),
        "joint_ci": bootstrap_mean(by_case(rows, "joint_correct")),
        "joint_ef_ci": bootstrap_mean(
            by_case([x for x in rows if x["key"] in error_free], "joint_correct")
        ),
        "joint_cov": pct([x["joint_correct"] for x in ok if x.get("joint_correct") is not None]),
        "n_unavail": sum(1 for x in ok if x["tool_unavailable"]),
        "ece": ece([(float(x.get("confidence") or 0), float(x["skill_correct"])) for x in ok]),
        "cost_ci": bootstrap_mean(by_case(cost_rows, "cost_usd")),
        "p50_ci": bootstrap_stat(by_case(cost_rows, "latency_ms"), np.median),
        "mcnemar": mcnemar(joint, ref) if ref is not None and name != REFERENCE else None,
        "resolved_by": dict(Counter(x["resolved_by"] for x in ok)),
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

    keys = set.intersection(*({x["key"] for x in res} for res in entries.values()))
    error_free = keys & set.intersection(
        *({x["key"] for x in res if not x["error"]} for res in entries.values())
    )
    costed = error_free & set.intersection(
        *(
            {x["key"] for x in res if not x["error"] and x.get("cost_usd") is not None}
            for res in entries.values()
        )
    )
    ref_rows = entries.get(REFERENCE) or []
    ref = {
        x["key"]: 0.0 if x["error"] else x.get("joint_correct") or 0.0
        for x in ref_rows
        if x["key"] in keys
    }
    stats = [entry_stats(n, res, keys, error_free, costed, ref) for n, res in entries.items()]

    print(f"# shadow run {args.shadow.name}: {len(rows)} rows\n")
    print(
        f"scorer {prov['scorer_hash']} | dataset {prov['dataset']['sha256'][:12]} | "
        f"run git {prov['run_git_sha']} | intention to treat over {len(keys)} (case, rep) keys "
        f"(an error row counts as wrong); sensitivity: {len(error_free)} keys error-free for "
        f"every entry; cost/latency over {len(costed)} keys every entry fully simulated\n"
    )
    print(
        "| entry | n | err | err % | skill % | joint % 95% CI (ITT) | joint % error-free ∩ "
        "(sensitivity) | joint cov. % | n_unavail | ECE | US$/1k routing 95% CI "
        "| p50 ms 95% CI | McNemar joint vs E5 (entry/E5 only) | resolved_by |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in stats:
        print(
            f"| {s['name']} | {s['n']} | {s['errors']} | {s['err_pct']} | {s['skill']} "
            f"| {fmt_ci(s['joint_ci'])} | {fmt_ci(s['joint_ef_ci'])} "
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
