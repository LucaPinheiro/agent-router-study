"""Accuracy / cost / latency per run, from RESCORED results files only (`study rescore`).

- Runs of one mode are compared on the intersection of their error-free case ids (M4).
- Columns are labelled by what they measure (L1): routing-only `tool_top1` (router's top-1)
  vs e2e `tool_first_call` (executor's first business call, or clarification credit).
- Headline: joint (skill and tool) accuracy for routing-only, e2e success (with and without
  invented arguments, H3) for e2e, each with a paired cluster-bootstrap 95% CI, plus the
  study cost / p50 latency CIs and an exact McNemar test against E5 on shared (case, rep).
- Cost (B6): `$study/case` is the ORIGINAL cost of every decision (cache-independent, what
  a production run pays); `$paid` is what this run was billed (cache hits free);
  `$list/case` is list price without prompt-cache discount (L2; needs `rescore --prices`).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from statistics import mean, quantiles
from typing import Any

import numpy as np

from routing_study.eval.rescore import read_rescored
from routing_study.eval.stats import bootstrap_mean, bootstrap_stat, fmt_ci, mcnemar

REFERENCE = "e5_llm_sonnet"
COLUMNS = {
    "routing-only": (
        ("skill%", "skill_correct"),
        ("tool_top1%", "tool_correct"),
        ("joint%", "joint_correct"),
        ("abst%", "abstain_correct"),
    ),
    "e2e": (
        ("skill%", "skill_correct"),
        ("tool_first_call%", "tool_correct"),
        ("args%", "args_valid"),
        ("e2e%", "e2e_success"),
        ("e2e_strict%", "e2e_strict"),
        ("invented%", "args_invented"),
        ("abst%", "abstain_correct"),
        ("grnd%", "grounded"),
    ),
}
HEADLINE = {"routing-only": "joint_correct", "e2e": "e2e_success"}


def load_results(paths: Iterable[Path]) -> list[dict[str, Any]]:
    """Rows of rescored files; a raw results file raises (reports never read raw scores)."""
    rows: list[dict[str, Any]] = []
    for p in paths:
        rows += read_rescored(p)[1]
    return rows


def _p(values: list[float], q: int) -> float:
    if len(values) < 2:
        return values[0] if values else 0.0
    return quantiles(values, n=100, method="inclusive")[q - 1]


def _latency(r: dict[str, Any]) -> float:
    """Routing latency, plus the executor's in e2e (turn latency includes harness time)."""
    lat = r["latency_ms"]
    return float(lat.get("routing") or 0.0) + float(lat.get("executor") or 0.0)


def _by_case(rows: list[dict[str, Any]], value: Any) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for r in rows:
        v = value(r)
        if v is not None:
            out.setdefault(r["case_id"], []).append(float(v))
    return out


def shared_cases(groups: dict[str, list[dict[str, Any]]]) -> set[str]:
    """Case ids that every run scored without an error (M4)."""
    sets = []
    for rs in groups.values():
        bad = {r["case_id"] for r in rs if r.get("error")}
        sets.append({r["case_id"] for r in rs} - bad)
    return set.intersection(*sets) if sets else set()


def _headline(rs: list[dict[str, Any]], shared: set[str], head: str) -> dict[Any, float]:
    return {
        (r["case_id"], r["rep"]): float(r["scores"][head])
        for r in rs
        if r["case_id"] in shared and r["scores"].get(head) is not None
    }


def summarize(rows: list[dict[str, Any]], reference: str = REFERENCE) -> list[dict[str, Any]]:
    by_mode: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for r in rows:
        by_mode.setdefault(r["mode"], {}).setdefault(r["run_name"], []).append(r)
    out = []
    for mode, groups in by_mode.items():
        shared = shared_cases(groups)
        head = HEADLINE[mode]
        ref = next((rs for rs in groups.values() if rs[0]["config"] == reference), None)
        ref_scores = _headline(ref, shared, head) if ref else None
        for name, rs in groups.items():
            ok = [r for r in rs if r["case_id"] in shared]
            row: dict[str, Any] = {
                "run": name,
                "config": rs[0]["config"],
                "mode": mode,
                "n": len(rs),
                "errors": sum(1 for r in rs if r.get("error")),
                "n_shared": len(ok),
                "cases_shared": len(shared),
            }
            for _, s in COLUMNS[mode]:
                row[s] = [float(r["scores"][s]) for r in ok if r["scores"].get(s) is not None]
            row["headline_ci"] = bootstrap_mean(_by_case(ok, lambda r, h=head: r["scores"].get(h)))
            if mode == "e2e":
                row["strict_ci"] = bootstrap_mean(
                    _by_case(ok, lambda r: r["scores"].get("e2e_strict"))
                )
            row["cost_ci"] = bootstrap_mean(_by_case(ok, lambda r: r["cost_usd"]["total"]))
            row["latency_ci"] = bootstrap_stat(_by_case(ok, _latency), np.median)
            row["paid_total"] = sum(
                float(r["cost_usd"].get("billed_total") or 0.0) for r in rs if "calls" in r
            )
            row["study_total"] = sum(float(r["cost_usd"].get("total") or 0.0) for r in ok)
            lst = [r["cost_usd"].get("list_uncached") for r in ok]
            row["list_case"] = mean(lst) if lst and None not in lst else None  # type: ignore[arg-type]
            turn = [float(r["latency_ms"]["turn"]) for r in ok]
            row["turn_p50"] = _p(turn, 50)
            rt = [float(r["latency_ms"]["routing"]) for r in ok]
            ex = [float(r["latency_ms"]["executor"]) for r in ok if r["latency_ms"].get("executor")]
            row["routing_p50"], row["routing_p95"] = _p(rt, 50), _p(rt, 95)
            row["executor_p50"], row["executor_p95"] = (
                (_p(ex, 50), _p(ex, 95)) if ex else (None, None)
            )
            resolved: dict[str, int] = {}
            for r in ok:
                key = r["scores"].get("resolved_by") or "-"
                resolved[key] = resolved.get(key, 0) + 1
            row["resolved_by"] = resolved
            row["mcnemar"] = (
                mcnemar(_headline(rs, shared, head), ref_scores)
                if ref_scores is not None and rs is not ref
                else None
            )
            out.append(row)
    return out


def _pct(values: list[float]) -> str:
    return f"{100 * mean(values):.1f}" if values else "-"


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def _mc(m: tuple[int, int, int, float] | None) -> str:
    return "-" if m is None else f"{m[1]}/{m[2]} p={m[3]:.3g}"


def render(paths: Iterable[Path], reference: str = REFERENCE) -> str:
    summary = summarize(load_results(paths), reference)
    lines: list[str] = []
    for mode in ("routing-only", "e2e"):
        rows = [r for r in summary if r["mode"] == mode]
        if not rows:
            continue
        head = HEADLINE[mode]
        cols = [c for c, _ in COLUMNS[mode]]
        header = (
            ["run", "n", "err", "n_shared"]
            + cols
            + [f"{head} 95% CI"]
            + (["e2e_strict 95% CI"] if mode == "e2e" else [])
            + ["$study/case 95% CI (x1000)", "$paid total", "$list/case", "p50 ms 95% CI"]
            + ["rt_p95", "ex_p50", "ex_p95", f"McNemar vs {reference} (run-only/ref-only)"]
            + ["resolved_by"]
        )
        lines += [
            f"## {mode}: {rows[0]['cases_shared']} case ids error-free in every run",
            "",
            "| " + " | ".join(header) + " |",
            "|" + "---|" * len(header),
        ]
        for r in rows:
            cells = [r["run"], str(r["n"]), str(r["errors"]), str(r["n_shared"])]
            cells += [_pct(r[s]) for _, s in COLUMNS[mode]]
            cells.append(fmt_ci(r["headline_ci"]))
            if mode == "e2e":
                cells.append(fmt_ci(r["strict_ci"]))
            cells += [
                fmt_ci(r["cost_ci"], scale=1000.0, digits=4),
                f"{r['paid_total']:.4f}",
                "-" if r["list_case"] is None else f"{r['list_case']:.5f}",
                fmt_ci(r["latency_ci"], scale=1.0, digits=0),
                _ms(r["routing_p95"]),
                _ms(r["executor_p50"]),
                _ms(r["executor_p95"]),
                _mc(r["mcnemar"]),
                ",".join(f"{k}:{v}" for k, v in sorted(r["resolved_by"].items())),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)
