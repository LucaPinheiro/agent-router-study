"""Accuracy / cost / latency table per run, from the local results files."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from statistics import mean, quantiles
from typing import Any

SCORES = ("skill_correct", "tool_correct", "args_valid", "e2e_success", "abstain_correct",
          "grounded")


def load_results(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in paths:
        rows += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return rows


def _pct(values: list[float]) -> str:
    return f"{100 * mean(values):5.1f}" if values else "    -"


def _p(values: list[float], q: int) -> float:
    if len(values) < 2:
        return values[0] if values else 0.0
    return quantiles(values, n=100, method="inclusive")[q - 1]


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(r["run_name"], []).append(r)
    out = []
    for name, rs in groups.items():
        ok = [r for r in rs if not r.get("error")]
        row: dict[str, Any] = {"run": name, "config": rs[0]["config"], "mode": rs[0]["mode"],
                               "n": len(rs), "errors": len(rs) - len(ok)}
        for s in SCORES:
            row[s] = [float(r["scores"][s]) for r in ok if r["scores"].get(s) is not None]
        lat = [r["latency_ms"]["turn"] for r in ok]
        row["cost_case"] = mean(r["cost_usd"]["total"] for r in ok) if ok else 0.0
        row["cost_routing"] = mean(r["cost_usd"]["routing"] for r in ok) if ok else 0.0
        row["cost_total"] = sum(r["cost_usd"]["total"] for r in ok)
        row["p50_ms"], row["p95_ms"] = _p(lat, 50), _p(lat, 95)
        row["routing_ms"] = mean(r["latency_ms"]["routing"] for r in ok) if ok else 0.0
        resolved: dict[str, int] = {}
        for r in ok:
            key = r["scores"].get("resolved_by") or "-"
            resolved[key] = resolved.get(key, 0) + 1
        row["resolved_by"] = resolved
        out.append(row)
    return out


def render(paths: Iterable[Path]) -> str:
    summary = summarize(load_results(paths))
    head = (f"{'run':<44} {'n':>4} {'err':>3} {'skill%':>6} {'tool%':>6} {'args%':>6} "
            f"{'e2e%':>6} {'abst%':>6} {'grnd%':>6} {'$/case':>9} {'$route':>9} {'$total':>8} "
            f"{'p50ms':>7} {'p95ms':>7} {'rt_ms':>6}  resolved_by")
    lines = [head, "-" * len(head)]
    for r in summary:
        lines.append(
            f"{r['run'][:44]:<44} {r['n']:>4} {r['errors']:>3} "
            + " ".join(f"{_pct(r[s]):>6}" for s in SCORES)
            + f" {r['cost_case']:>9.5f} {r['cost_routing']:>9.5f} {r['cost_total']:>8.4f}"
            f" {r['p50_ms']:>7.0f} {r['p95_ms']:>7.0f} {r['routing_ms']:>6.0f}  "
            + ",".join(f"{k}:{v}" for k, v in sorted(r["resolved_by"].items())))
    return "\n".join(lines)
