# ruff: noqa: E501  (report prose and table rows)
"""Enterprise decision matrix: latency SLO x cost ceiling x minimum joint accuracy -> the best
qualifying routing configuration on test-v2 (results/analysis/enterprise_matrix.md).

Qualification uses POINT estimates (warm p95 from the lat-* benchmark; observed routing
US$/1k; ITT joint); each cell also says whether the 95% CIs support the claim (joint CI lower
bound >= the floor, p95 CI upper bound < the SLO, cost CI upper bound <= the ceiling). Best =
highest joint point estimate, ties -> lower cost. Only configurations with a latency benchmark
can qualify (E3 ablations and the exploratory x-* runs have none).
"""

from __future__ import annotations

from typing import Any

from final_common import OUT, md_table, write, write_json

SLO_MS = (50, 500, 2000, 10000)
COST_1K = (0.0, 0.5, 2.0, 10.0)
MIN_JOINT = (0.75, 0.80, 0.85)


def candidates(est: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for k, s in est["strategies"].items():
        lat = est["latency"].get(s.get("lat") or "")
        if not lat:
            continue
        out.append(
            {
                "key": k,
                "label": s["label"],
                "status": s["status"],
                "joint": s["joint"],
                "cost": {x: 1000 * v for x, v in s["cost_observed_per_case"].items()},
                "cost_list": {x: 1000 * v for x, v in s["cost_list_uncached_per_case"].items()},
                "p95": lat["warm"]["95"],
                "local": lat["local"],
            }
        )
    return out


def _local_line(cands: list[dict[str, Any]]) -> str:
    loc = sorted((c for c in cands if c["local"]), key=lambda c: -c["joint"]["point"])
    if not loc:
        return "- No local configuration was benchmarked."
    b = loc[0]
    fast = [c for c in loc if c["p95"]["point"] < 2000]
    f = fast[0] if fast else None
    s = f"- Best local (US$ 0) configuration: {b['label']} {100 * b['joint']['point']:.1f}% at p95 {b['p95']['point']:.0f} ms"
    if f is not None and f is not b:
        s += f"; best local under p95 2 s: {f['label']} {100 * f['joint']['point']:.1f}% at p95 {f['p95']['point']:.0f} ms"
    return s + "."


def run_enterprise(est: dict[str, Any]) -> dict[str, Any]:
    cands = candidates(est)
    lines = [
        "# Enterprise decision matrix (test-v2, routing-only)",
        "",
        "For each latency SLO (warm p95, dedicated lat-* benchmark), routing-cost ceiling (US$ per 1 000 cases, observed regime) and "
        "minimum joint accuracy (ITT), the qualifying configuration with the highest joint accuracy (ties: lower cost). Qualification "
        "uses point estimates; `robust` = the 95% CIs also satisfy all three constraints (joint CI lower bound >= floor, p95 CI upper "
        "bound < SLO, cost CI upper bound <= ceiling). Estimation only (no test); the paired differences between the top candidates are "
        "in primary.md / secondary.md and mostly within a few pp with overlapping CIs, so a cell's winner is not 'significantly best'.",
        "",
        "Caveats: routing-only joint (not e2e success: see estimation.md J, where every routed config is below the native E0 executor); "
        "latency measured on one machine / one network at concurrency 1 (API latency includes provider queueing); local model cost is "
        "counted as US$ 0 (hardware and energy excluded); Jev's cost is its reported OpenRouter price (no list price).",
        "",
        "## Candidates",
        "",
    ]
    lines += md_table(
        [
            "config",
            "where",
            "joint % [95% CI]",
            "warm p95 ms [95% CI]",
            "US$/1k observed [95% CI]",
            "US$/1k list uncached",
        ],
        [
            [
                c["label"],
                "local" if c["local"] else "API",
                f"{100 * c['joint']['point']:.1f} [{100 * c['joint']['lo']:.1f}, {100 * c['joint']['hi']:.1f}]",
                f"{c['p95']['point']:.1f} [{c['p95']['lo']:.1f}, {c['p95']['hi']:.1f}]",
                f"{c['cost']['point']:.3f} [{c['cost']['lo']:.3f}, {c['cost']['hi']:.3f}]",
                f"{c['cost_list']['point']:.3f}",
            ]
            for c in sorted(cands, key=lambda c: -c["joint"]["point"])
        ],
    )
    cells = []
    for floor in MIN_JOINT:
        rows = []
        for slo in SLO_MS:
            row = [f"p95 < {slo:g} ms"]
            for ceil in COST_1K:
                q = [
                    c
                    for c in cands
                    if c["p95"]["point"] < slo
                    and c["cost"]["point"] <= ceil + 1e-12
                    and c["joint"]["point"] >= floor
                ]
                if not q:
                    row.append("none qualifies")
                    cells.append({"floor": floor, "slo_ms": slo, "cost_1k": ceil, "best": None})
                    continue
                b = sorted(q, key=lambda c: (-c["joint"]["point"], c["cost"]["point"]))[0]
                robust = (
                    b["joint"]["lo"] >= floor
                    and b["p95"]["hi"] < slo
                    and b["cost"]["hi"] <= ceil + 1e-12
                )
                row.append(
                    f"**{b['key']}** {100 * b['joint']['point']:.1f} [{100 * b['joint']['lo']:.1f}, {100 * b['joint']['hi']:.1f}] · "
                    f"p95 {b['p95']['point']:.0f} ms · US$ {b['cost']['point']:.2f}/1k · {'robust' if robust else 'not robust'}"
                    + (
                        f" (also: {', '.join(c['key'] for c in q if c is not b)})"
                        if len(q) > 1
                        else ""
                    )
                )
                cells.append(
                    {
                        "floor": floor,
                        "slo_ms": slo,
                        "cost_1k": ceil,
                        "best": b["key"],
                        "robust": robust,
                        "qualifying": [c["key"] for c in q],
                    }
                )
            rows.append(row)
        lines += [f"## Minimum joint accuracy {100 * floor:.0f}%", ""]
        lines += md_table(
            ["latency SLO \\ cost ceiling"] + [f"<= US$ {c:g}/1k" for c in COST_1K], rows
        )
    best_any = sorted(cands, key=lambda c: -c["joint"]["point"])[:1]
    lines += [
        "## Reading",
        "",
        f"- Highest joint point estimate among benchmarked configs: {best_any[0]['label']} ({100 * best_any[0]['joint']['point']:.1f}%)."
        if best_any
        else "",
        _local_line(cands),
        "- Cells marked `none qualifies` are a result (no benchmarked configuration meets all three constraints), not missing data.",
        "",
    ]
    write(OUT / "enterprise_matrix.md", "\n".join(lines))
    js = {"candidates": cands, "cells": cells}
    write_json(OUT / "enterprise_matrix.json", js)
    return js
