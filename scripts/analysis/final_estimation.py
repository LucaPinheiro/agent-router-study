# ruff: noqa: E501  (report prose and table rows)
"""Estimation tables (prereg-v1 "Estimation only" + labelled exploratory items) on test-v2.

Writes results/analysis/estimation.md and estimation.json (the figure and enterprise-matrix
inputs). Descriptive: CIs, no tests. Every number comes from the rescored rows.
"""

from __future__ import annotations

import csv
import importlib
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

import numpy as np
import yaml
from final_common import (
    CATEGORIES,
    E2E_VARIANCE,
    LAT,
    LAT_LOCAL,
    OUT,
    PARETO_DEV,
    QPS_GRID,
    REPEATS,
    ROOT,
    SHADOW,
    V1,
    Context,
    by_case,
    ci_json,
    complete,
    dev_maps,
    fms,
    fmt,
    fnum,
    md_table,
    modelled_cache_cost,
    multi_label,
    prefix_sizes,
    raw_conf,
    resolving_step,
    row_list_uncached,
    rows_of,
    run_status,
    write,
    write_json,
)

from routing_study.eval import calibrate as cal
from routing_study.eval.metrics import (
    abstention_pr,
    calibration,
    joint_confidence,
    recall_at_k,
    risk_coverage,
)
from routing_study.eval.report import itt
from routing_study.eval.rescore import config_models
from routing_study.eval.simulate import aggregate, simulate_rows
from routing_study.eval.stats import bootstrap_mean, bootstrap_stat
from routing_study.settings import load_settings

LLM_STRATS = ("llm", "llm_local", "jev")


def _cfg_yaml(config: str) -> dict[str, Any]:
    p = ROOT / "config" / "experiments" / f"{config}.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


# ------------------------------------------------------------------ A. per strategy


def strategy_table(ctx: Context, prefixes: dict) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    acc_rows, cost_rows = [], []
    for k, rs in ctx.routing.items():
        run = ctx.runs[k]
        reps = max(r["rep"] for r in rs)
        n_err = sum(1 for r in rs if r.get("error"))
        skill = bootstrap_mean(by_case(rs, lambda r: itt(r, "skill_correct")))
        cond_tool = bootstrap_mean(
            by_case(
                rs,
                lambda r: (
                    (r["scores"].get("tool_correct") or 0.0)
                    if (not r.get("error") and r["scores"].get("skill_correct"))
                    else None
                ),
            )
        )
        joint = bootstrap_mean(by_case(rs, lambda r: itt(r, "joint_correct")))
        first = bootstrap_mean(by_case(rs, lambda r: itt(r, "joint_first_label")))
        abst = bootstrap_mean(by_case(rs, lambda r: itt(r, "abstain_correct")))
        rec = {
            kk: bootstrap_mean(by_case(rs, lambda r, kk=kk: recall_at_k(r, kk))) for kk in (1, 2, 3)
        }
        ap = abstention_pr(rs)
        obs = bootstrap_mean(by_case(rs, lambda r: (r.get("cost_usd") or {}).get("routing")))
        lst_vals = [row_list_uncached(r) for r in rs]
        lst = bootstrap_mean(
            by_case(
                [{"case_id": r["case_id"], "v": v[0]} for r, v in zip(rs, lst_vals, strict=True)],
                lambda x: x["v"],
            )
        )
        jev_reported = any(v[1] for v in lst_vals)
        modelled = {q: modelled_cache_cost(rs, q, prefixes) for q in QPS_GRID}
        modelled["inf"] = modelled_cache_cost(rs, float("inf"), prefixes)
        acc_rows.append(
            [
                run.label,
                run.status,
                len(rs),
                reps,
                f"{n_err} ({100 * n_err / len(rs):.1f}%)",
                fmt(skill),
                fmt(cond_tool),
                fmt(joint),
                fmt(first),
                fmt(abst),
                fmt(rec[1]),
                fmt(rec[2]),
                fmt(rec[3]),
                f"{fnum(ap['precision'])} ({ap['n_abstained']})",
                f"{fnum(ap['recall'])} ({ap['n_expected']})",
            ]
        )
        cost_rows.append(
            [
                run.label,
                fmt(obs, 1000, 3),
                fmt(lst, 1000, 3) + (" (Jev: reported, no list price)" if jev_reported else ""),
            ]
            + [f"{1000 * modelled[q]:.3f}" for q in QPS_GRID]
            + [f"{1000 * modelled['inf']:.3f}"]
        )
        js[k] = {
            "run": run.name,
            "label": run.label,
            "family": run.family,
            "status": run.status,
            "lat": run.lat,
            "local": run.local,
            "rows": len(rs),
            "reps": reps,
            "errors": n_err,
            "skill": ci_json(skill),
            "tool_given_skill": ci_json(cond_tool),
            "joint": ci_json(joint),
            "joint_first_label": ci_json(first),
            "abstain_correct": ci_json(abst),
            "recall": {kk: ci_json(v) for kk, v in rec.items()},
            "abstention": ap,
            "cost_observed_per_case": ci_json(obs),
            "cost_list_uncached_per_case": ci_json(lst),
            "list_uses_jev_reported": jev_reported,
            "cost_modelled_cache_per_case": {str(q): v for q, v in modelled.items()},
        }
    lines = ["## A. Per strategy (routing-only, ITT; % with 95% cluster-bootstrap CI)", ""]
    lines += md_table(
        [
            "router",
            "status",
            "rows",
            "reps",
            "error rows",
            "skill %",
            "tool % given correct skill",
            "joint % (primary metric)",
            "joint first-label % (strict)",
            "abstain_correct %",
            "recall@1",
            "recall@2",
            "recall@3",
            "abstention precision % (n abstained)",
            "abstention recall % (n expected)",
        ],
        acc_rows,
    )
    lines += [
        "### Routing cost per 1 000 cases (US$), three regimes",
        "",
        "- **observed**: the recorded cost of every consulted decision, with the provider prompt cache as it was when the decision was first computed "
        "(warm cache: runs share the shadow pass's samples; cache-independent of the response cache) — the pre-registered regime of the H1 co-primary;",
        "- **list uncached**: recorded tokens x list price, no prompt-cache discount (config/prices.yaml; Jev has no list price, its reported OpenRouter cost is used; local = 0);",
        "- **modelled cache**: Poisson arrivals at the given QPS, 5-minute TTL refreshed on hit, per prompt prefix (model, level, static prompt); "
        "hit probability 1 - exp(-QPS x share x 300 s); cacheable prefix = the largest cache read+write ever observed for that prefix "
        "(Haiku prompts never cached: below the provider minimum). `∞` = every call a cache hit. Model, not measurement.",
        "",
    ]
    lines += md_table(
        ["router", "observed [95% CI]", "list uncached [95% CI]"]
        + [f"modelled @ {q:g} QPS" for q in QPS_GRID]
        + ["modelled ∞"],
        cost_rows,
    )
    return lines, js


# ------------------------------------------------------------------ B/C. calibration + risk


def _cal_pairs(
    rows: list[dict[str, Any]], level: str, config: str
) -> dict[str, list[tuple[float, float]]]:
    cfg = _cfg_yaml(config).get("strategies") or {}
    models = config_models(config)
    maps = dev_maps()
    out: dict[str, list[tuple[float, float]]] = {"raw": [], "deployed": [], "dev_map": []}
    kinds: Counter[str] = Counter()
    for r in rows:
        d = r.get(level) or {}
        s = r.get("scores") or {}
        if r.get("error") or not d.get("choice"):
            continue
        if level == "tool" and not s.get("skill_correct"):
            continue
        key = "skill_correct" if level == "skill" else "tool_correct"
        if s.get(key) is None:
            continue
        ok = float(s[key])
        st = resolving_step(d) or {}
        dep = float(d.get("confidence") or 0.0)
        raw = raw_conf(st)
        raw = dep if raw is None else raw
        strat = st.get("strategy")
        deployed_map = level in ((cfg.get(strat) or {}).get("calibration") or {})
        out["raw"].append((raw, ok))
        out["deployed"].append((dep, ok))
        if deployed_map:
            out["dev_map"].append((dep, ok))
            kinds["deployed"] += 1
        elif strat in LLM_STRATS and level in maps.get(models.get(strat, ""), {}):
            x, y = maps[models[strat]][level]
            out["dev_map"].append((float(np.interp(raw, x, y)), ok))
            kinds["post-hoc"] += 1
        else:
            out["dev_map"].append((dep, ok))
            kinds["none"] += 1
    out["_kinds"] = kinds  # type: ignore[assignment]
    return out


def calibration_table(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    rows_md, risk_md = [], []
    for k, rs in ctx.routing.items():
        run = ctx.runs[k]
        js[k] = {}
        for level in ("skill", "tool"):
            pairs = _cal_pairs(rs, level, rs[0]["config"])
            kinds = pairs.pop("_kinds")
            c = {name: calibration(p) for name, p in pairs.items()}
            js[k][level] = {name: v for name, v in c.items()} | {"map_kind": dict(kinds)}
            if c["raw"] is None:
                continue
            map_label = ", ".join(f"{kk} {vv}" for kk, vv in kinds.items())
            rows_md.append(
                [
                    run.label,
                    level,
                    c["raw"]["n"],
                    f"{c['raw']['brier']:.3f} / {c['raw']['ece']:.3f}",
                    f"{c['deployed']['brier']:.3f} / {c['deployed']['ece']:.3f}",
                    f"{c['dev_map']['brier']:.3f} / {c['dev_map']['ece']:.3f}",
                    map_label,
                ]
            )
        rc = risk_coverage((joint_confidence(r), itt(r, "joint_correct") or 0.0) for r in rs)
        js[k]["risk"] = rc
        risk_md.append(
            [run.label, f"{rc['aurc']:.3f}", fnum(rc["coverage_at_risk"]), fnum(1 - rc["risk"][-1])]
        )
    lines = [
        "## B. Calibration on test-v2: Brier / ECE (10 equal-mass bins), raw vs dev-calibrated",
        "",
        "Per decision made (abstentions and error rows out); tool level only on rows with a correct skill. "
        "`raw` = the router's own score (usage raw_confidence / confidence_raw); `deployed` = the confidence the run used "
        "(dev map applied where the pre-registered rule ece_cal < ece_raw kept it); `dev map` = the dev-fitted map applied "
        "to every decision that has one, including LLM stages where it was NOT deployed (post hoc, exploratory). "
        "For cascades the resolving step's score is used.",
        "",
    ]
    lines += md_table(
        [
            "router",
            "level",
            "n decisions",
            "raw Brier / ECE",
            "deployed Brier / ECE",
            "dev map Brier / ECE",
            "map used (decisions)",
        ],
        rows_md,
    )
    lines += [
        "## C. Selective prediction: risk-coverage on joint (confidence = min(skill, tool))",
        "",
    ]
    lines += md_table(
        ["router", "AURC (lower = better)", "coverage % at risk <= 5%", "joint % at full coverage"],
        risk_md,
    )
    return lines, js


# ------------------------------------------------------------------ D. latency


def _lat_rows(strategy: str) -> list[tuple[int, int, dict[str, Any]]]:
    out = []
    for b in (1, 2, 3, 4):
        rs = rows_of(f"lat-{strategy}-b{b}")
        if rs is None:
            continue
        out += [(b, i, r) for i, r in enumerate(rs)]
    return out


def latency_table(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    md = []
    for s in LAT:
        rows = _lat_rows(s)
        if not rows:
            continue
        warm = [
            (r["case_id"], float(r["latency_ms"]["routing"]))
            for b, i, r in rows
            if i > 0 and not r.get("error")
        ]
        cold = [float(r["latency_ms"]["routing"]) for b, i, r in rows if i == 0]
        groups: dict[str, list[float]] = defaultdict(list)
        for c, v in warm:
            groups[c].append(v)
        pct = {
            q: bootstrap_stat(groups, lambda a, q=q: float(np.percentile(a, q)))
            for q in (50, 95, 99)
        }
        errs = sum(1 for _, _, r in rows if r.get("error"))
        joint = mean(itt(r, "joint_correct") or 0.0 for _, _, r in rows)
        blocks = sorted({b for b, _, _ in rows})
        js[s] = {
            "local": s in LAT_LOCAL,
            "n_warm": len(warm),
            "n_cold": len(cold),
            "blocks": blocks,
            "errors": errs,
            "warm": {str(q): ci_json(v) for q, v in pct.items()},
            "cold_ms": cold,
            "warm_values": [v for _, v in warm],
            "bench_joint": joint,
        }
        md.append(
            [
                s,
                "local" if s in LAT_LOCAL else "API",
                len(blocks),
                len(warm),
                fms(pct[50]),
                fms(pct[95]),
                fms(pct[99]),
                (
                    f"{median(cold):.2f} / {max(cold):.2f}"
                    if max(cold) < 10
                    else f"{median(cold):.0f} / {max(cold):.0f}"
                )
                if cold
                else "-",
                errs,
            ]
        )
    lines = [
        "## D. Latency (dedicated benchmark lat-*, ONLY source of latency numbers)",
        "",
        "100 stratified test-v2 cases in 4 blocks of 25, block-level interleaving of the 12 strategies, concurrency 1, "
        "response cache off and a fresh vector cache. Routing latency (skill + tool stage) per case. The first case of each "
        "block is **cold** (reported apart: median / max over the 4 blocks); the remaining 96 are **warm**. 95% CIs: cluster "
        "bootstrap over cases. p99 of 96 values is close to the sample maximum: read it as a tail indicator. API = network call "
        "to Bedrock / OpenRouter (includes queueing at the provider); local = this machine (Apple Silicon, Ollama for qwen/embedding).",
        "",
    ]
    lines += md_table(
        [
            "strategy",
            "where",
            "blocks",
            "warm n",
            "p50 ms [95% CI]",
            "p95 ms [95% CI]",
            "p99 ms [95% CI]",
            "cold first case ms median / max",
            "error rows",
        ],
        md,
    )
    return lines, js


# ------------------------------------------------------------------ E. breakdowns


MAIN_BREAKDOWN = ("E1", "E2", "E3", "E10", "E11", "E6b", "E4", "E5", "E6", "E7", "E8", "E9")


def breakdowns(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    keys = [k for k in MAIN_BREAKDOWN if k in ctx.routing]
    js: dict[str, Any] = {"category": {}, "tool": {}, "labels": {}}
    cat_rows = []
    for k in keys:
        rs = ctx.routing[k]
        row = [ctx.runs[k].label]
        js["category"][k] = {}
        for c in CATEGORIES:
            sub = [r for r in rs if r.get("category") == c]
            ci = bootstrap_mean(by_case(sub, lambda r: itt(r, "joint_correct")))
            js["category"][k][c] = ci_json(ci)
            row.append(fmt(ci))
        cat_rows.append(row)
    n_cat = (
        Counter(r["category"] for r in ctx.routing[keys[0]] if r["rep"] == 1) if keys else Counter()
    )
    lines = ["## E. Breakdowns (descriptive; no tests)", "", "### Joint % by category [95% CI]", ""]
    lines += md_table(["router"] + [f"{c} (n={n_cat.get(c, 0)})" for c in CATEGORIES], cat_rows)
    lines += [
        "ambiguo labels are weak (auditor A accepted 23/70 test-v2 ambiguous label sets): the ambiguo column is reported apart on purpose.",
        "",
    ]
    # per tool (gold first acceptable tool)
    tools = (
        Counter(
            (r["expected"]["acceptable_tools"] or ["?"])[0]
            for r in ctx.routing[keys[0]]
            if r["rep"] == 1
        )
        if keys
        else Counter()
    )
    tool_rows = []
    for t, n in sorted(tools.items(), key=lambda kv: (-kv[1], kv[0])):
        row = [t, n]
        for k in keys:
            sub = [
                r for r in ctx.routing[k] if (r["expected"]["acceptable_tools"] or ["?"])[0] == t
            ]
            v = mean(itt(r, "joint_correct") or 0.0 for r in sub) if sub else None
            js["tool"].setdefault(k, {})[t] = v
            row.append(fnum(v, digits=0))
        tool_rows.append(row)
    lines += ["### Joint % by gold (first-listed) tool, point estimates", ""]
    lines += md_table(["gold tool", "n cases"] + keys, tool_rows)
    # single vs multi-label
    lab_rows = []
    for k in keys:
        rs = ctx.routing[k]
        row = [ctx.runs[k].label]
        js["labels"][k] = {}
        for name, flag in (("single", False), ("multi", True)):
            sub = [r for r in rs if multi_label(r["expected"]) == flag]
            j = bootstrap_mean(by_case(sub, lambda r: itt(r, "joint_correct")))
            f = bootstrap_mean(by_case(sub, lambda r: itt(r, "joint_first_label")))
            js["labels"][k][name] = {"joint": ci_json(j), "joint_first_label": ci_json(f)}
            row += [fmt(j), fmt(f)]
        lab_rows.append(row)
    n_multi = (
        sum(1 for r in ctx.routing[keys[0]] if r["rep"] == 1 and multi_label(r["expected"]))
        if keys
        else 0
    )
    lines += [
        f"### Single- vs multi-label gold ({349 - n_multi} single, {n_multi} multi-label cases)",
        "",
    ]
    lines += md_table(
        [
            "router",
            "single: joint %",
            "single: first-label %",
            "multi: joint % (any label)",
            "multi: first-label % (strict)",
        ],
        lab_rows,
    )
    lines += [
        "### Seed vs synthetic",
        "",
        "Not applicable on test-v2: all 349 cases are `source: synthetic_v2` (google/gemini-2.5-flash); test-v2 has **no seed cases** "
        "(docs/dataset-card.md). The seed-vs-synthetic stratification applies to test-v1 only (see section K when the v1 runs complete).",
        "",
    ]
    return lines, js


# ------------------------------------------------------------------ G. repeats


def _flip(rs_a: list[dict[str, Any]], rs_b: list[dict[str, Any]]) -> dict[str, Any]:
    a = {r["case_id"]: r for r in rs_a}
    b = {r["case_id"]: r for r in rs_b}
    shared = sorted(set(a) & set(b))
    dec = {
        c: float(
            ((a[c].get("skill") or {}).get("choice"), (a[c].get("tool") or {}).get("choice"))
            != ((b[c].get("skill") or {}).get("choice"), (b[c].get("tool") or {}).get("choice"))
        )
        for c in shared
    }
    cor = {
        c: float((itt(a[c], "joint_correct") or 0.0) != (itt(b[c], "joint_correct") or 0.0))
        for c in shared
    }
    return {
        "n": len(shared),
        "decision_flip": ci_json(bootstrap_mean({c: [v] for c, v in dec.items()})),
        "joint_flip": ci_json(bootstrap_mean({c: [v] for c, v in cor.items()})),
        "decision_flips": int(sum(dec.values())),
        "joint_flips": int(sum(cor.values())),
    }


def repeats(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    md = []
    for label, (rep_run, _main) in REPEATS.items():
        rs = rows_of(rep_run)
        if rs is None:
            md.append([label, "not complete", "", "", ""])
            continue
        r1 = [r for r in rs if r["rep"] == 1]
        r2 = [r for r in rs if r["rep"] == 2]
        f = _flip(r1, r2)
        js[label] = f
        md.append(
            [
                label,
                f["n"],
                f"{f['decision_flips']} ({fmt([f['decision_flip'][x] for x in ('point', 'lo', 'hi')])})",
                f"{f['joint_flips']} ({fmt([f['joint_flip'][x] for x in ('point', 'lo', 'hi')])})",
                "rep 1 = cache hit of the main run; rep 2 fresh",
            ]
        )
    for k in ("E4", "E5", "E7", "E8", "E9"):
        rs = ctx.routing.get(k)
        if not rs:
            continue
        reps = sorted({r["rep"] for r in rs})
        if len(reps) < 2:
            continue
        f = _flip([r for r in rs if r["rep"] == reps[0]], [r for r in rs if r["rep"] == reps[1]])
        js[f"{k} rep1 vs rep2"] = f
        md.append(
            [
                f"{ctx.runs[k].label}: rep 1 vs rep 2 (349 cases)",
                f["n"],
                f"{f['decision_flips']} ({fmt([f['decision_flip'][x] for x in ('point', 'lo', 'hi')])})",
                f"{f['joint_flips']} ({fmt([f['joint_flip'][x] for x in ('point', 'lo', 'hi')])})",
                "within the 3-rep run (independent samples)",
            ]
        )
    lines = [
        "## G. Repetition flip rates (determinism)",
        "",
        "decision flip = (skill, tool) choice differs between the two reps; joint flip = correctness differs. % [95% CI] over cases.",
        "",
    ]
    lines += md_table(
        ["check", "cases", "decision flips n (% [CI])", "joint flips n (% [CI])", "note"], md
    )
    return lines, js


# ------------------------------------------------------------------ H. Jev served models


def jev_served(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    md = []
    for k in ("E4", "E7", "E9"):
        rs = ctx.routing.get(k)
        if not rs:
            continue
        stats: dict[tuple[str, str], list[float]] = defaultdict(list)
        mix: Counter[tuple[str, str]] = Counter()
        for r in rs:
            s = r.get("scores") or {}
            for lv in ("skill", "tool"):
                for st in (r.get(lv) or {}).get("steps") or []:
                    if st.get("strategy") != "jev":
                        continue
                    m = (st.get("usage") or {}).get("served_model") or "(none: error)"
                    mix[(lv, m)] += 1
                    resolved = (r.get(lv) or {}).get("resolved_by") == "jev"
                    if not resolved or r.get("error"):
                        continue
                    if lv == "skill":
                        stats[(lv, m)].append(float(s.get("skill_correct") or 0.0))
                    elif s.get("skill_correct"):
                        stats[(lv, m)].append(float(s.get("tool_correct") or 0.0))
        js[k] = {
            f"{lv}|{m}": {
                "calls": n,
                "resolved_n": len(stats[(lv, m)]),
                "acc": mean(stats[(lv, m)]) if stats[(lv, m)] else None,
            }
            for (lv, m), n in mix.items()
        }
        tot = Counter()
        for (lv, _), n in mix.items():
            tot[lv] += n
        for (lv, m), n in sorted(mix.items(), key=lambda kv: (kv[0][0], -kv[1])):
            acc = stats[(lv, m)]
            md.append(
                [
                    ctx.runs[k].label,
                    lv,
                    m,
                    n,
                    f"{100 * n / tot[lv]:.1f}",
                    len(acc),
                    fnum(mean(acc)) if acc else "-",
                ]
            )
    lines = [
        "## H. Jev served-model mix and accuracy by served model (EXPLORATORY, descriptive)",
        "",
        "Jev is a meta-router: each call is served by a model it picks. Accuracy = skill_correct (skill level) or tool_correct given a correct skill (tool level), "
        "over the decisions Jev resolved. Served model is confounded with case difficulty (Jev's choice depends on the input): no causal reading.",
        "",
    ]
    lines += md_table(
        ["run", "level", "served model", "calls", "share %", "resolved decisions", "accuracy %"], md
    )
    return lines, js


# ------------------------------------------------------------------ I. cascades


def _parse_th(s: str) -> dict[str, float]:
    s = (s or "").strip()
    if s in ("", "-"):
        return {}
    return {kv.split("=")[0].strip(): float(kv.split("=")[1]) for kv in s.split(",")}


def _unavail(t: Any, pick: Any) -> int:
    """Rows whose tool stage cannot be replayed at this threshold choice (counted 0)."""
    i = cal.outcome_index(t.skill_conf, t.skill_ok, t.skill_last, np.array([pick[0]], float))[0]
    j = cal.outcome_index(t.tool_conf, t.tool_ok, t.tool_last, np.array([pick[1]], float))[0]
    return int(sum(bool(t.unavail[x, i[x], j[x]]) for x in range(len(t.keys))))


CASCADE_CFG = {
    "E7": "e7_regex_jev",
    "E8": "e8_regex_llm",
    "E9": "e9_regex_jev_llm",
    "E12": "e12_hybrid_jev_llm",
}


def cascades(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {"coverage": {}, "shadow": {}}
    lines = [
        "## I. Cascades",
        "",
        "### Coverage per step (real runs; share of rows resolved at each step, and accuracy there)",
        "",
    ]
    md = []
    for k in ("E7", "E8", "E9", "E12"):
        rs = ctx.routing.get(k)
        if not rs:
            continue
        js["coverage"][k] = {}
        for lv in ("skill", "tool"):
            by: dict[str, list[float]] = defaultdict(list)
            for r in rs:
                if r.get("error"):
                    by["(error)"].append(0.0)
                    continue
                st = (r.get(lv) or {}).get("resolved_by") or (
                    "(no tool stage)" if lv == "tool" else "(abstained)"
                )
                s = r["scores"]
                if lv == "skill":
                    by[st].append(float(s.get("skill_correct") or 0.0))
                else:
                    by[st].append(
                        float(s.get("tool_correct") or 0.0)
                        if s.get("skill_correct")
                        else float("nan")
                    )
            for st, vals in by.items():
                ok = [v for v in vals if v == v]
                js["coverage"][k][f"{lv}|{st}"] = {
                    "n": len(vals),
                    "share": len(vals) / len(rs),
                    "acc": mean(ok) if ok else None,
                }
                md.append(
                    [
                        ctx.runs[k].label,
                        lv,
                        st,
                        len(vals),
                        f"{100 * len(vals) / len(rs):.1f}",
                        fnum(mean(ok)) if ok else "-",
                    ]
                )
    lines += md_table(
        [
            "run",
            "stage",
            "resolved by",
            "rows",
            "share %",
            "accuracy % (skill; tool given correct skill)",
        ],
        md,
    )

    shadow = rows_of(SHADOW)
    if shadow is None:
        return lines + ["(shadow run not complete: no simulated Pareto)", ""], js
    shadow = [r for r in shadow if (r.get("skill") or {}).get("shadow")]
    ccs = importlib.import_module("calibrate_cascades")
    dev_pts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with PARETO_DEV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            dev_pts[row["experiment"]].append(row)
    sim_md, ref_md = [], []
    for k, cfg in CASCADE_CFG.items():
        settings = load_settings(ROOT / "config" / "experiments" / f"{cfg}.yaml")
        mode = settings.routing.mode
        sk_names = cal.tuned_steps(settings.routing.skill, mode)
        tl_names = cal.tuned_steps(settings.routing.tool, mode)
        t = cal.build_tables(shadow, settings)
        frozen = cal.configured(settings)
        sim = aggregate(simulate_rows(shadow, settings))
        real = ctx.routing.get(k)
        real_joint = mean(itt(r, "joint_correct") or 0.0 for r in real) if real else None
        fz = cal.summarize(cal.row_values(t, *frozen))
        entry: dict[str, Any] = {
            "frozen": {
                "skill": dict(zip(sk_names, frozen[0], strict=True)),
                "tool": dict(zip(tl_names, frozen[1], strict=True)),
                "joint": ci_json(fz["joint_ci"]),
                "cost": ci_json(fz["cost_ci"]),
            },
            "simulate_rows_joint": sim["joint_acc"],
            "real_run_joint": real_joint,
            "dev_front": [],
            "refs": {},
        }
        status = "exploratory" if k == "E12" else "estimation"
        entry["frozen"]["unavailable_rows"] = _unavail(t, frozen)
        sim_md.append(
            [
                k,
                status,
                "frozen (D5, method (a))",
                ", ".join(f"{a}={b:g}" for a, b in entry["frozen"]["skill"].items()) or "-",
                ", ".join(f"{a}={b:g}" for a, b in entry["frozen"]["tool"].items()) or "-",
                fmt(fz["joint_ci"]),
                _unavail(t, frozen),
                fmt(fz["cost_ci"], 1000, 3),
                fnum(real_joint) if real_joint is not None else "not run",
            ]
        )
        for p in dev_pts.get(cfg, []):
            sk = _parse_th(p["skill_thresholds"])
            tl = _parse_th(p["tool_thresholds"])
            pick = (
                tuple(sk.get(n, 0.0) for n in sk_names),
                tuple(tl.get(n, 0.0) for n in tl_names),
            )
            sm = cal.summarize(cal.row_values(t, *pick))
            entry["dev_front"].append(
                {
                    "skill": sk,
                    "tool": tl,
                    "dev_joint": float(p["joint_acc"]),
                    "dev_cost_1k": float(p["cost_usd_per_1k"]),
                    "test_joint": ci_json(sm["joint_ci"]),
                    "test_cost": ci_json(sm["cost_ci"]),
                }
            )
            sim_md.append(
                [
                    k,
                    "exploratory",
                    "dev Pareto point",
                    p["skill_thresholds"],
                    p["tool_thresholds"],
                    fmt(sm["joint_ci"]),
                    _unavail(t, pick),
                    fmt(sm["cost_ci"], 1000, 3),
                    f"dev {100 * float(p['joint_acc']):.1f} @ {float(p['cost_usd_per_1k']):.2f}",
                ]
            )
        never = ccs.NEVER
        picks = {
            "always-last (final router alone)": (
                (never,) * len(sk_names),
                (never,) * len(tl_names),
            ),
            "always-first (every step accepts)": ((0.0,) * len(sk_names), (0.0,) * len(tl_names)),
        }
        refs = {lab: cal.summarize(cal.row_values(t, *pk)) for lab, pk in picks.items()}
        refs["oracle (best stopping step per row)"] = cal.summarize(ccs.oracle_rows(t))
        for lab, sm in refs.items():
            ua = _unavail(t, picks[lab]) if lab in picks else "-"
            entry["refs"][lab] = {
                "joint": ci_json(sm["joint_ci"]),
                "cost": ci_json(sm["cost_ci"]),
                "unavailable_rows": ua,
            }
            ref_md.append([k, lab, fmt(sm["joint_ci"]), ua, fmt(sm["cost_ci"], 1000, 3)])
        rd = ccs.random_deferral(t, frozen, 200, 0)
        entry["refs"]["random deferral at frozen rates"] = {
            "joint": rd["joint"] / 100,
            "cost_1k": rd["cost_1k"],
        }
        ref_md.append(
            [
                k,
                "random deferral at the frozen thresholds' acceptance rates (200 draws, mean)",
                f"{rd['joint']:.1f}",
                "-",
                f"{rd['cost_1k']:.3f}",
            ]
        )
        # in-sample front on test (optimistic, exploratory)
        g = cal.grid()
        gs = cal.grid_sums(t, cal.combos_of(g, len(sk_names)), cal.combos_of(g, len(tl_names)))
        front = cal.pareto_front(gs)
        entry["test_insample_front"] = [
            {
                "skill": f["skill"],
                "tool": f["tool"],
                "joint": f["joint_acc"],
                "cost_1k": 1000 * f["cost"],
            }
            for f in front
        ]
        js["shadow"][k] = entry
    lines += [
        "### Simulated cascades on the test-v2 shadow pass (v2-shadow-tuned-routing-r3, 349 cases x 3 reps)",
        "",
        "Replay of the recorded decisions through the same pipeline code (`eval.calibrate` fast tables, cross-checked against `eval.simulate`). "
        "Joint ITT with a tool stage that cannot be replayed counted 0 (lower bound); cost over covered rows. Frozen = the pre-registered "
        "thresholds; dev Pareto points = docs/results/cascade-pareto-dev.csv replayed on test (EXPLORATORY, prereg §5). "
        "The last column compares with the real run (same samples).",
        "",
        "**Simulated joint is a LOWER BOUND.** The shadow pass recorded the tool-stage decisions only under the skill that E9 chose; "
        "when a simulated cascade picks a different (correct) skill its tool stage cannot be replayed and counts 0 (`unavail.` column). "
        "This is why frozen E7/E8 points can sit below their real runs and why always-last (Sonnet / Jev alone) reads below the real "
        "E5 / E4 runs. Compare simulated points with each other, never with real runs.",
        "",
    ]
    lines += md_table(
        [
            "cascade",
            "status",
            "point",
            "skill thresholds",
            "tool thresholds",
            "test joint % [95% CI]",
            "unavail. rows (of 1047)",
            "test US$/1k [95% CI]",
            "real run joint % / dev",
        ],
        sim_md,
    )
    lines += ["### References on the test shadow (no fit; same lower-bound caveat)", ""]
    lines += md_table(["cascade", "reference", "joint %", "unavail. rows", "US$/1k"], ref_md)
    lines += [
        'The always-last reference of E8/E9 is "always-LLM" (Sonnet alone at every stage, on the shadow\'s Sonnet samples); '
        "always-last of E7 is Jev alone. The oracle is an upper bound for any deferral rule; a threshold rule is only worth "
        "something if it beats random deferral at the same acceptance rates. An in-sample Pareto front fitted on test (optimistic, "
        "exploratory) is in estimation.json (`cascades.shadow.<E>.test_insample_front`) and drawn faintly in the Pareto figure.",
        "",
    ]
    return lines, js


# ------------------------------------------------------------------ J. e2e


E2E_SCORES = (
    ("skill_correct", "skill"),
    ("tool_correct", "tool first call"),
    ("args_valid", "args valid"),
    ("e2e_success", "e2e_success"),
    ("first_call_success", "= first call"),
    ("clarification_credited", "+ clarification"),
    ("recovered_credited", "+ recovered"),
    ("e2e_strict", "e2e_strict"),
    ("args_invented", "args_invented (rate, lower = better)"),
    ("entity_grounded", "entity_grounded"),
)


def e2e(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    md, cost_md = [], []
    for k, rs in ctx.e2e.items():
        run = ctx.e2e_runs[k]
        row = [run.label, len(rs), sum(1 for r in rs if r.get("error"))]
        js[k] = {"run": run.name, "label": run.label, "family": run.family}
        for s, _ in E2E_SCORES:
            ci = bootstrap_mean(by_case(rs, lambda r, s=s: itt(r, s)))
            js[k][s] = ci_json(ci)
            row.append(fmt(ci))
        md.append(row)
        tot = bootstrap_mean(by_case(rs, lambda r: (r.get("cost_usd") or {}).get("total")))
        rt = bootstrap_mean(by_case(rs, lambda r: (r.get("cost_usd") or {}).get("routing")))
        ag = bootstrap_mean(by_case(rs, lambda r: (r.get("cost_usd") or {}).get("agent")))
        lst = bootstrap_mean(by_case(rs, lambda r: row_list_uncached(r)[0]))
        ctxt = bootstrap_mean(by_case(rs, lambda r: (r.get("tokens") or {}).get("prompt")))
        cached = sum((r.get("tokens") or {}).get("cached", 0) for r in rs) / max(
            1, sum((r.get("tokens") or {}).get("prompt", 0) for r in rs)
        )
        calls = mean((r.get("tokens") or {}).get("agent_calls", 0) for r in rs)
        comp = bootstrap_mean(by_case(rs, lambda r: (r.get("tokens") or {}).get("completion")))
        js[k] |= {
            "cost_turn": ci_json(tot),
            "cost_routing": ci_json(rt),
            "cost_executor": ci_json(ag),
            "cost_list": ci_json(lst),
            "prompt_tokens": ci_json(ctxt),
            "completion_tokens": ci_json(comp),
            "cached_share": cached,
            "executor_calls": calls,
        }
        cost_md.append(
            [
                run.label,
                fmt(tot, 1000, 2),
                fmt(rt, 1000, 2),
                fmt(ag, 1000, 2),
                fmt(lst, 1000, 2),
                fmt(ctxt, 1, 0),
                f"{100 * cached:.1f}",
                fmt(comp, 1, 0),
                f"{calls:.2f}",
            ]
        )
    lines = [
        "## J. End-to-end (executor Sonnet 5, 1 rep, 349 cases; ITT, % [95% CI])",
        "",
        "e2e_success = first call + clarification + recovered (disjoint, docs/metrics.md). args_invented and entity_grounded are not applicable to error rows.",
        "",
    ]
    lines += md_table(["run", "rows", "errors"] + [lab for _, lab in E2E_SCORES], md)
    lines += [
        "### Cost per turn and context",
        "",
        "US$ per 1 000 turns (observed = recorded; list = no prompt-cache discount, Jev reported). Context = executor prompt tokens per turn (all agent calls).",
        "",
    ]
    lines += md_table(
        [
            "run",
            "US$/1k turns total [CI]",
            "routing [CI]",
            "executor [CI]",
            "list uncached total [CI]",
            "executor prompt tokens/turn [CI]",
            "cached share of prompt tokens %",
            "completion tokens/turn [CI]",
            "executor calls/turn",
        ],
        cost_md,
    )
    # executor variance
    var_md = []
    for k, name in E2E_VARIANCE.items():
        rs = rows_of(name)
        if rs is None or k not in ctx.e2e:
            var_md.append([k, name, "not complete", "", ""])
            continue
        main = {r["case_id"]: r for r in ctx.e2e[k]}
        shared = [r for r in rs if r["case_id"] in main]
        flips = [
            float((itt(r, "e2e_success") or 0) != (itt(main[r["case_id"]], "e2e_success") or 0))
            for r in shared
        ]
        a = mean(itt(r, "e2e_success") or 0 for r in shared)
        b = mean(itt(main[r["case_id"]], "e2e_success") or 0 for r in shared)
        ci = bootstrap_mean({r["case_id"]: [f] for r, f in zip(shared, flips, strict=True)})
        js.setdefault("executor_variance", {})[k] = {
            "n": len(shared),
            "flip": ci_json(ci),
            "rep2": a,
            "main": b,
        }
        var_md.append([k, name, len(shared), fmt(ci), f"{100 * b:.1f} -> {100 * a:.1f}"])
    lines += [
        "### Executor variance (second e2e run on 60 cases; routers are cache hits, executor resampled)",
        "",
    ]
    lines += md_table(
        ["exp", "run", "cases", "e2e_success flip % [CI]", "e2e_success main -> rep2 (same cases)"],
        var_md,
    )
    return lines, js


# ------------------------------------------------------------------ K. extras (slot-in)


def extras(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    lines = ["## K. Slot-in sections (filled when the runs complete)", ""]
    v1_md = []
    for k, name in V1.items():
        rs = rows_of(name)
        if rs is None:
            v1_md.append([k, name, "not complete", "", "", ""])
            continue
        j1 = bootstrap_mean(by_case(rs, lambda r: itt(r, "joint_correct")))
        j2 = (
            bootstrap_mean(by_case(ctx.routing[k], lambda r: itt(r, "joint_correct")))
            if k in ctx.routing
            else None
        )
        src = Counter(r.get("source") for r in rs)
        js.setdefault("v1", {})[k] = {"test_v1": ci_json(j1), "test_v2": ci_json(j2)}
        v1_md.append(
            [k, name, len(rs), fmt(j1), fmt(j2), dict(src) if any(src) else "source not in rows"]
        )
    lines += [
        "### test-v1 (exposed split) free-router replication (EXPLORATORY: contamination check)",
        "",
    ]
    lines += md_table(
        ["router", "run", "rows", "test-v1 joint %", "test-v2 joint %", "sources"], v1_md
    )
    try:
        from routing_study.eval.manifest import load_manifest
        from routing_study.eval.rq5 import held_out_tools, load_rq5_rows, render

        m = load_manifest(ROOT / "config" / "study_manifest.yaml")
        names = [r.name for r in m.runs if r.name.startswith("rq5-") and complete(r.name)]
        data = load_rq5_rows(names, ROOT / "results" / "rescored") if names else None
        if data:
            lines += [
                "### RQ5 leave-tools-out (EXPLORATORY; `study rq5` table, no re-train timing)",
                "",
                render(data, held_out_tools(), "test_v2", None),
                "",
            ]
            js["rq5_runs"] = names
        else:
            lines += [
                "### RQ5 leave-tools-out (EXPLORATORY)",
                "",
                "No complete rq5-test_v2-* run yet.",
                "",
            ]
    except Exception as exc:  # noqa: BLE001 - optional section; report and continue
        lines += [f"(RQ5 section unavailable: {type(exc).__name__}: {exc})", ""]
    return lines, js


def run_estimation(ctx: Context) -> dict[str, Any]:
    all_rows = [r for rs in ctx.routing.values() for r in rs]
    shadow = rows_of(SHADOW) or []
    prefixes = prefix_sizes(all_rows + shadow)
    st = run_status()
    lines = [
        '# Estimation tables: test-v2 (prereg-v1 "estimation only"; exploratory items labelled)',
        "",
        "Generated by `scripts/analysis/final_all.py`. Intention to treat; 95% CIs = cluster bootstrap over case ids (10k, seed 20260930). "
        "No tests here (descriptive). Runs included only when their rescored file exists and the manifest log says COMPLETE.",
        "",
        "Runs not (yet) complete and therefore absent: " + (", ".join(ctx.missing) or "none") + ".",
        "",
    ]
    out: dict[str, Any] = {"missing": ctx.missing, "status": st}
    for name, fn in (
        ("strategies", lambda: strategy_table(ctx, prefixes)),
        ("calibration", lambda: calibration_table(ctx)),
        ("latency", lambda: latency_table(ctx)),
        ("breakdowns", lambda: breakdowns(ctx)),
        ("repeats", lambda: repeats(ctx)),
        ("jev", lambda: jev_served(ctx)),
        ("cascades", lambda: cascades(ctx)),
        ("e2e", lambda: e2e(ctx)),
        ("extras", lambda: extras(ctx)),
    ):
        md, js = fn()
        lines += md
        out[name] = js
        print(f"  estimation: {name} done", flush=True)
    write(OUT / "estimation.md", "\n".join(lines))
    write_json(OUT / "estimation.json", out)
    return out


__all__ = ["run_estimation", "Path"]
