"""Accuracy / cost / latency per run, from RESCORED results files only (`study rescore`).

- Intention to treat (F2, primary): every row counts; an error row (failed routing stage,
  crashed case) is WRONG for every correctness score and stays in the denominator. The error
  rate is its own column. The intersection of the case ids error-free in every run is a
  labelled SENSITIVITY table only.
- Columns are labelled by what they measure (L1): routing-only `tool_top1` (router's top-1)
  vs e2e `tool_first_call` (executor's first business call, or clarification credit).
- Headline: joint (skill and tool) accuracy for routing-only, e2e success (with and without
  invented arguments, H3) for e2e, each with a cluster-bootstrap 95% CI, plus the study cost
  / p50 latency CIs.
- Contrasts (F4): explicit `run - reference` pairs (never a hard-coded reference), each
  with the paired cluster-bootstrap CI of Δ, case-level McNemar and sign-flip p-values (per-case
  means over reps), Holm within its family and the NI / TOST verdict for margin kinds
  (`eval/stats.py`). `--reference X` is sugar for "every run vs X" in one family.
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

from routing_study.eval.metrics import (
    abstention_pr,
    baselines,
    calibration,
    joint_confidence,
    level_pairs,
    recall_at_k,
    risk_coverage,
    skill_tools_of,
)
from routing_study.eval.rescore import NA, load_dataset, load_tools, read_rescored
from routing_study.eval.stats import (
    Contrast,
    bootstrap_mean,
    bootstrap_stat,
    evaluate_contrasts,
    fmt_ci,
)

COLUMNS = {
    "routing-only": (
        ("skill%", "skill_correct"),
        ("tool_top1%", "tool_correct"),
        ("joint%", "joint_correct"),
        ("joint_1st_label%", "joint_first_label"),
        ("abst%", "abstain_correct"),
    ),
    "e2e": (
        ("skill%", "skill_correct"),
        ("tool_first_call%", "tool_correct"),
        ("args%", "args_valid"),
        ("e2e%", "e2e_success"),
        ("= first_call%", "first_call_success"),
        ("+ clarif%", "clarification_credited"),
        ("+ recovered%", "recovered_credited"),
        ("e2e_strict%", "e2e_strict"),
        ("invented%", "args_invented"),
        ("joint_1st_label%", "joint_first_label"),
        ("abst%", "abstain_correct"),
        ("entity_grnd%", "entity_grounded"),
    ),
}
ALIASES = {"entity_grounded": "grounded"}  # pre-F6 rows carry the old name
HEADLINE = {"routing-only": "joint_correct", "e2e": "e2e_success"}
# correctness scores: an error row counts 0 for these (ITT); other scores (rates of a bad
# outcome such as args_invented, or grounded) are not applicable to an error row
CORRECTNESS = frozenset(
    (
        "skill_correct",
        "tool_correct",
        "joint_correct",
        "abstain_correct",
        "args_valid",
        "e2e_success",
        "e2e_strict",
        "joint_first_label",
        "first_call_success",
        "clarification_credited",
        "recovered_credited",
    )
)


def itt(r: dict[str, Any], score: str) -> float | None:
    """A row's score under intention to treat: an error row is wrong (0) for correctness
    scores and has no value for the others."""
    if r.get("error"):
        return 0.0 if score in CORRECTNESS else None
    scores = r.get("scores") or {}
    v = scores.get(score, scores.get(ALIASES.get(score, ""), None))
    return None if v is None else float(v)


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


def _headline(rs: list[dict[str, Any]], keys: set[str] | None, head: str) -> dict[Any, float]:
    """(case_id, rep) -> ITT headline score, restricted to `keys` case ids when given."""
    return {
        (r["case_id"], r["rep"]): v
        for r in rs
        if (keys is None or r["case_id"] in keys) and (v := itt(r, head)) is not None
    }


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One summary row per run, grouped by (split, mode): runs of different splits are
    never pooled or intersected (F7)."""
    by_group: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    for r in rows:
        key = (str(r.get("split") or "?"), r["mode"])
        by_group.setdefault(key, {}).setdefault(r["run_name"], []).append(r)
    out = []
    for (split, mode), groups in by_group.items():
        shared = shared_cases(groups)
        head = HEADLINE[mode]
        for name, rs in groups.items():
            ok = [r for r in rs if not r.get("error")]
            errors = len(rs) - len(ok)
            row: dict[str, Any] = {
                "run": name,
                "config": rs[0]["config"],
                "mode": mode,
                "split": split,
                "n": len(rs),
                "errors": errors,
                "error_rate": errors / len(rs) if rs else 0.0,
                "n_shared": sum(1 for r in rs if r["case_id"] in shared),
                "cases_shared": len(shared),
            }
            for _, s in COLUMNS[mode]:
                row[s] = [v for r in rs if (v := itt(r, s)) is not None]
            row["headline_ci"] = bootstrap_mean(_by_case(rs, lambda r, h=head: itt(r, h)))
            row["error_free_ci"] = bootstrap_mean(
                _by_case([r for r in rs if r["case_id"] in shared], lambda r, h=head: itt(r, h))
            )
            if mode == "e2e":
                row["strict_ci"] = bootstrap_mean(_by_case(rs, lambda r: itt(r, "e2e_strict")))
            row["cost_ci"] = bootstrap_mean(_by_case(ok, lambda r: r["cost_usd"]["total"]))
            row["latency_ci"] = bootstrap_stat(_by_case(ok, _latency), np.median)
            row["paid_total"] = sum(
                float(r["cost_usd"].get("billed_total") or 0.0) for r in rs if "calls" in r
            )
            row["study_total"] = sum(float(r["cost_usd"].get("total") or 0.0) for r in ok)
            lst = [r["cost_usd"].get("list_uncached") for r in ok]
            row["list_case"] = (
                NA
                if NA in lst
                else mean(lst)  # type: ignore[arg-type]
                if lst and None not in lst
                else None
            )
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
            row["recall"] = {
                k: mean(vs)
                if (vs := [v for r in rs if (v := recall_at_k(r, k)) is not None])
                else None
                for k in (1, 2, 3)
            }
            row["abstention"] = abstention_pr(rs)
            routed = [r for r in rs if not r.get("native")]
            row["risk"] = risk_coverage((joint_confidence(r), itt(r, head) or 0.0) for r in routed)
            row["cal"] = {lv: calibration(level_pairs(rs, lv)) for lv in ("skill", "tool")}
            row["headline_scores"] = _headline(rs, None, head)
            out.append(row)
    return out


def _pct(values: list[float]) -> str:
    return f"{100 * mean(values):.1f}" if values else "-"


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def _mc(m: tuple[int, int, int, float] | None) -> str:
    return "-" if m is None else f"{m[1]}/{m[2]} p={m[3]:.3g}"


def _pval(p: float | None) -> str:
    return "-" if p is None else f"{p:.3g}"


def contrast_scores(rows: list[dict[str, Any]]) -> dict[str, dict[Any, float]]:
    """name -> (case, rep) -> ITT headline, by run name and, when unique, by config name."""
    out: dict[str, dict[Any, float]] = {r["run"]: r["headline_scores"] for r in rows}
    by_config: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_config.setdefault(r["config"], []).append(r)
    for config, rs in by_config.items():
        if len(rs) == 1:
            out.setdefault(config, rs[0]["headline_scores"])
    return out


def render_contrasts(rows: list[dict[str, Any]], contrasts: list[Contrast], head: str) -> list[str]:
    results = evaluate_contrasts(contrast_scores(rows), contrasts)
    lines = [
        f"### contrasts on {head} (joint for routing-only, e2e_success for e2e; case level: "
        "per-case means over reps; Holm within family)",
        "",
        "| family | run | reference | kind | n cases | Δ pp 95% CI (paired bootstrap) "
        "| McNemar case-level (run-only/ref-only) | sign-flip p | Holm p | reject | verdict |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for res in results:
        c = res["contrast"]
        kind = c.kind if c.kind in ("two_sided", "greater") else f"{c.kind} ±{100 * c.margin:g}pp"
        if "missing" in res:
            lines.append(
                f"| {c.family} | {c.run} | {c.reference} | {kind} | - | missing run "
                f"{res['missing']} | | | | | |"
            )
            continue
        v = res.get("verdict") or {}
        verdict = (
            ("non-inferior" if v["non_inferior"] else "not shown")
            if "non_inferior" in v
            else v.get("conclusion") or "-"
        )
        lines.append(
            f"| {c.family} | {c.run} | {c.reference} | {kind} | {res['n_cases']} "
            f"| {fmt_ci(res['delta_ci'])} | {_mc(res['mcnemar'])} | {_pval(res['p'])} "
            f"| {_pval(res.get('p_holm'))} | {'yes' if res.get('reject') else 'no'} | {verdict} |"
        )
    return lines + [""]


def _f(x: float | None, pct: bool = True, digits: int = 1) -> str:
    if x is None:
        return "-"
    return f"{100 * x:.{digits}f}" if pct else f"{x:.{digits + 2}f}"


def _cal(c: dict[str, Any] | None) -> str:
    if not c:
        return "-"
    bins = "/".join(str(b[0]) for b in c["bins"])
    return f"{c['brier']:.3f} / {c['ece']:.3f} (n={c['n']}; bins {bins})"


def render_secondary(rows: list[dict[str, Any]], mode: str, head: str) -> list[str]:
    lines = [
        f"### {mode} secondary metrics (docs/metrics.md)",
        "",
        "| run | recall@1 | recall@2 | recall@3 | abst. precision | abst. recall (n expected) "
        f"| AURC ({head}) | coverage @5% risk | skill Brier / ECE (adaptive bins) "
        "| tool Brier / ECE |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        a, rk = r["abstention"], r["risk"]
        lines.append(
            f"| {r['run']} | {_f(r['recall'][1])} | {_f(r['recall'][2])} | {_f(r['recall'][3])} "
            f"| {_f(a['precision'])} | {_f(a['recall'])} ({a['n_expected']}) "
            f"| {_f(rk['aurc'], pct=False) if rk else '-'} "
            f"| {_f(rk['coverage_at_risk']) if rk else '-'} "
            f"| {_cal(r['cal']['skill'])} | {_cal(r['cal']['tool'])} |"
        )
    return lines + [""]


def render_baselines(rows: list[dict[str, Any]]) -> list[str]:
    """Trivial routers on the cases of these runs (golds from the rescored rows; majority
    fitted on dev; catalog from mcp_server/tools_list.json)."""
    cases = {r["case_id"]: {"expected": r["expected"]} for r in rows if r.get("expected")}
    try:
        dev = list(load_dataset("dev")[0].values())
        table = baselines(list(cases.values()), dev, skill_tools_of(load_tools()))
    except (OSError, ValueError, KeyError) as exc:
        return [f"(trivial baselines unavailable: {exc})", ""]
    lines = [
        f"### trivial baselines on these {len(cases)} cases (majority fitted on dev)",
        "",
        "| baseline | skill% | tool% | joint% | abst% |",
        "|---|---|---|---|---|",
    ]
    for name, m in table.items():
        lines.append(
            f"| {name} | {_f(m['skill_correct'])} | {_f(m['tool_correct'])} "
            f"| {_f(m['joint_correct'])} | {_f(m['abstain_correct'])} |"
        )
    return lines + [""]


def default_contrasts(rows: list[dict[str, Any]], reference: str) -> list[Contrast]:
    """Every run vs `reference` (a run or config name), two-sided, in one family."""
    names = contrast_scores(rows)
    if reference not in names:
        return []
    ref = names[reference]
    return [
        Contrast(r["run"], reference, family=f"vs {reference}")
        for r in rows
        if r["headline_scores"] is not ref
    ]


def render(
    paths: Iterable[Path],
    reference: str | None = None,
    contrasts: list[Contrast] | None = None,
    with_baselines: bool = True,
) -> str:
    raw = load_results(paths)
    summary = summarize(raw)
    lines: list[str] = []
    wanted = list(contrasts or [])
    groups = sorted(
        {(r["split"], r["mode"]) for r in summary},
        key=lambda g: (g[0], ("routing-only", "e2e").index(g[1])),
    )
    for split, mode in groups:
        rows = [r for r in summary if (r["split"], r["mode"]) == (split, mode)]
        group_rows = [r for r in raw if (str(r.get("split") or "?"), r["mode"]) == (split, mode)]
        head = HEADLINE[mode]
        cols = [c for c, _ in COLUMNS[mode]]
        header = (
            ["run", "n", "err", "err%"]
            + cols
            + [f"{head} 95% CI"]
            + (["e2e_strict 95% CI"] if mode == "e2e" else [])
            + ["$study/case 95% CI (x1000)", "$paid total", "$list/case", "p50 ms 95% CI"]
            + ["rt_p95", "ex_p50", "ex_p95", "resolved_by"]
        )
        lines += [
            f"## {split} / {mode}: intention to treat (an error row counts as wrong)",
            "",
            "runs: " + ", ".join(r["run"] for r in rows),
            "",
            "| " + " | ".join(header) + " |",
            "|" + "---|" * len(header),
        ]
        for r in rows:
            cells = [r["run"], str(r["n"]), str(r["errors"]), f"{100 * r['error_rate']:.1f}"]
            cells += [_pct(r[s]) for _, s in COLUMNS[mode]]
            cells.append(fmt_ci(r["headline_ci"]))
            if mode == "e2e":
                cells.append(fmt_ci(r["strict_ci"]))
            cells += [
                fmt_ci(r["cost_ci"], scale=1000.0, digits=4),
                f"{r['paid_total']:.4f}",
                "-"
                if r["list_case"] is None
                else r["list_case"]
                if r["list_case"] == NA
                else f"{r['list_case']:.5f}",
                fmt_ci(r["latency_ci"], scale=1.0, digits=0),
                _ms(r["routing_p95"]),
                _ms(r["executor_p50"]),
                _ms(r["executor_p95"]),
                ",".join(f"{k}:{v}" for k, v in sorted(r["resolved_by"].items())),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines += [
            "",
            f"### {split} / {mode} SENSITIVITY: {rows[0]['cases_shared']} case ids error-free "
            "in every run listed",
            "",
            f"| run | n_shared | {head} 95% CI (error-free intersection) |",
            "|---|---|---|",
        ]
        lines += [f"| {r['run']} | {r['n_shared']} | {fmt_ci(r['error_free_ci'])} |" for r in rows]
        lines.append("")
        if reference is not None:
            wanted += default_contrasts(rows, reference)
        lines += render_secondary(rows, mode, head)
        if mode == "routing-only" and with_baselines:
            lines += render_baselines(group_rows)
    if wanted:  # one evaluation: Holm families may span groups (e.g. H1-H3)
        lines += ["## contrasts", ""] + render_contrasts(summary, wanted, "the headline")
    return "\n".join(lines)
