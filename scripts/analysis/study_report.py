"""Per-strategy analysis of a shadow routing-only run (docs/estudo-resultados.md).

Usage: uv run python scripts/analysis/study_report.py <shadow.jsonl> [--single <run.jsonl> ...]

Skill stage: every strategy decided on every case, so accuracy is directly comparable.
Tool stage: shadow tool decisions exist only for the skill the recorded cascade loaded, so a
strategy's tool/joint accuracy is computed on the cases where its own skill choice equals the
loaded one (`n_cmp`); other cases count as joint-correct only through an abstention match.
`--single` adds real (non-shadow) single-strategy runs, e.g. E6 Haiku, whose LLM differs from
the shadow LLM.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, quantiles
from typing import Any

from routing_study.eval.simulate import simulate
from routing_study.routers.base import ABSTAIN
from routing_study.settings import load_settings

STRATEGIES = ("regex", "bm25", "embedding", "hybrid", "jev", "llm")
CATEGORIES = ("direto", "parafrase", "ambiguo", "multiturno", "fora_escopo", "adversarial")
CASCADES = ("e1_regex", "e2_bm25", "e3_embedding", "e4_jev", "e5_llm_sonnet", "e7_regex_jev",
            "e8_regex_llm", "e9_regex_jev_llm")


def load(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in rows if not r.get("error") and r.get("skill")]


def choice(d: dict[str, Any] | None) -> str:
    return (d or {}).get("choice") or ABSTAIN


def pct(xs: list[float]) -> str:
    return f"{100 * mean(xs):.1f}" if xs else "-"


def p(xs: list[float], q: int) -> float:
    return quantiles(xs, n=100, method="inclusive")[q - 1] if len(xs) > 1 else (xs or [0])[0]


def ece(pairs: list[tuple[float, float]], bins: int = 10) -> float:
    """Expected calibration error over (confidence, correct) pairs."""
    buckets: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for c, ok in pairs:
        buckets[min(int(max(c, 0.0) * bins), bins - 1)].append((c, ok))
    n = len(pairs)
    return sum(len(b) / n * abs(mean(c for c, _ in b) - mean(o for _, o in b))
               for b in buckets.values()) if n else 0.0


def strategy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for s in STRATEGIES:
        sk_ok, tl_ok, joint, cal, lat, cost = [], [], [], [], [], []
        by_cat: dict[str, list[float]] = defaultdict(list)
        n_cmp = 0
        for r in rows:
            exp = r["expected"]
            sd = r["skill"]["shadow"].get(s)
            if sd is None:
                continue
            sk = choice(sd)
            ok = float(sk in exp["acceptable_skills"])
            sk_ok.append(ok)
            by_cat[r["category"]].append(ok)
            cal.append((float(sd.get("confidence") or 0.0), ok))
            lat_case, cost_case = sd["latency_ms"], sd["cost_usd"]
            if sk == ABSTAIN:
                joint.append(float(ABSTAIN in exp["acceptable_tools"]))
            elif r.get("tool") and choice(r["skill"]) == sk and s in r["tool"]["shadow"]:
                td = r["tool"]["shadow"][s]
                t_ok = float(choice(td) in exp["acceptable_tools"])
                n_cmp += 1
                if ok:
                    tl_ok.append(t_ok)
                joint.append(ok * t_ok)
                lat_case += td["latency_ms"]
                cost_case += td["cost_usd"]
            elif not ok:
                joint.append(0.0)
            lat.append(lat_case)
            cost.append(cost_case)
        out.append({"strategy": s, "n": len(sk_ok), "skill": pct(sk_ok), "tool_cond": pct(tl_ok),
                    "joint": pct(joint), "n_joint": len(joint), "n_cmp": n_cmp,
                    "ece": f"{ece(cal):.3f}", "p50": p(lat, 50), "p95": p(lat, 95),
                    "usd_1k": 1000 * mean(cost) if cost else 0.0,
                    "by_cat": {c: pct(by_cat[c]) for c in CATEGORIES}})
    return out


def confusions(rows: list[dict[str, Any]], s: str, top: int = 5) -> list[tuple[str, int]]:
    c: Counter[str] = Counter()
    for r in rows:
        exp = r["expected"]
        sk = choice(r["skill"]["shadow"].get(s))
        if sk not in exp["acceptable_skills"]:
            c[f"skill {'/'.join(exp['acceptable_skills'])} -> {sk}"] += 1
        td = (r.get("tool") or {}).get("shadow", {}).get(s)
        if td and sk in exp["acceptable_skills"] and choice(td) not in exp["acceptable_tools"]:
            c[f"tool {'/'.join(exp['acceptable_tools'])} -> {choice(td)}"] += 1
    return c.most_common(top)


def single_run(path: Path) -> dict[str, Any]:
    rows = load(path)
    sk = [float(r["scores"]["skill_correct"]) for r in rows]
    tl = [float(r["scores"]["tool_correct"]) for r in rows if r["scores"]["skill_correct"]]
    jt = [float(r["scores"]["skill_correct"] and r["scores"]["tool_correct"]) for r in rows]
    lat = [r["latency_ms"]["routing"] for r in rows]
    by_cat: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(float(r["scores"]["skill_correct"]))
    return {"run": rows[0]["run_name"], "n": len(rows), "skill": pct(sk), "tool_cond": pct(tl),
            "joint": pct(jt), "p50": p(lat, 50), "p95": p(lat, 95),
            "usd_1k": 1000 * mean(r["cost_usd"]["routing"] for r in rows),
            "by_cat": {c: pct(by_cat[c]) for c in CATEGORIES}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("shadow", type=Path)
    ap.add_argument("--single", type=Path, nargs="*", default=[])
    args = ap.parse_args()
    rows = load(args.shadow)
    print(f"# shadow run {args.shadow.name}: {len(rows)} cases\n")
    print("## strategies (isolated)\n")
    print("| strategy | n | skill % | tool % (cond.) | joint % | n_cmp | ECE | p50 ms | p95 ms "
          "| US$/1k |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    strat = strategy_rows(rows)
    for r in strat:
        print(f"| {r['strategy']} | {r['n']} | {r['skill']} | {r['tool_cond']} | {r['joint']} "
              f"| {r['n_cmp']} | {r['ece']} | {r['p50']:.0f} | {r['p95']:.0f} "
              f"| {r['usd_1k']:.4f} |")
    singles = [single_run(x) for x in args.single]
    for r in singles:
        print(f"| {r['run']} (real run) | {r['n']} | {r['skill']} | {r['tool_cond']} "
              f"| {r['joint']} | {r['n']} | - | {r['p50']:.0f} | {r['p95']:.0f} "
              f"| {r['usd_1k']:.4f} |")
    print("\n## skill accuracy by category\n")
    print("| strategy | " + " | ".join(CATEGORIES) + " |")
    print("|---|" + "---|" * len(CATEGORIES))
    for r in strat + singles:
        name = r.get("strategy") or r["run"]
        print(f"| {name} | " + " | ".join(r["by_cat"][c] for c in CATEGORIES) + " |")
    print("\n## simulated cascades (offline replay of the shadow decisions)\n")
    print("| config | skill % | tool % | US$/1k routing | ms/case routing | resolved_by |")
    print("|---|---|---|---|---|---|")
    for c in CASCADES:
        s = simulate(args.shadow, load_settings(Path(f"config/experiments/{c}.yaml")))
        tool = f"{100 * s['tool_acc']:.1f} (n={s['tool_n']})" if s["tool_acc"] is not None else "-"
        print(f"| {c} | {100 * s['skill_acc']:.1f} | {tool} | {1000 * s['routing_cost_case']:.4f}"
              f" | {s['routing_ms_case']:.0f} | {s['resolved_by']} |")
    print("\n## top errors per strategy\n")
    for s in STRATEGIES:
        print(f"- **{s}**: " + "; ".join(f"{k} ({v})" for k, v in confusions(rows, s)))


if __name__ == "__main__":
    main()
