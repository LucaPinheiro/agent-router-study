# ruff: noqa: E501  (report prose and table rows)
"""EXPLORATORY end-to-end analyses on test-v2 (post hoc; never confirmatory).

1. Deviation D-002 (docs/prereg/deviations.md): `x-e9-fullskill-e2e-r1` and
   `x-e7-fullskill-e2e-r1` re-run E9 / E7 end to end with `routing.tool.expose_top_k: 5` (the
   routed skill's tools all exposed, plus the global tools) and are compared with their top-2
   counterparts and with native E0: e2e_success and its decomposition with paired CIs, cost
   per turn, tokens.
2. Error analysis of WHY routed e2e (E9, and the full-skill variant) is below native E0:
   every discordant paired case is put in exactly one class by an ordered rule list.

Hypothesis-generating only: the D-002 runs were designed after seeing the test-v2 H3 result,
on the same split; any claim needs a fresh split. Writes results/analysis/exploratory_e2e.{md,json}
and (figure step) estudos/figuras/final-x-*.png.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from statistics import mean
from typing import Any

from final_common import (
    OUT,
    Context,
    by_case,
    ci_json,
    fmt,
    md_table,
    paired_ratio,
    rows_of,
    write,
    write_json,
)

from routing_study.eval.report import itt
from routing_study.eval.scorers import business_calls
from routing_study.eval.stats import bootstrap_mean, mcnemar_cases, paired_delta, sign_flip

D002 = {
    "E9-full": ("x-e9-fullskill-e2e-r1", "E9 regex->Jev->Sonnet, all skill tools exposed", "E9"),
    "E7-full": ("x-e7-fullskill-e2e-r1", "E7 regex->Jev, all skill tools exposed", "E7"),
}
ABSTAIN = "__abstain__"
PARTS = (
    ("e2e_success", "e2e_success"),
    ("first_call_success", "= first call"),
    ("clarification_credited", "+ clarification"),
    ("recovered_credited", "+ recovered"),
    ("skill_correct", "skill"),
    ("tool_correct", "tool first call"),
    ("args_valid", "args valid"),
)


def _s(r: dict[str, Any], k: str) -> float:
    return float(itt(r, k) or 0.0)


def _keys(rows: list[dict[str, Any]], score: str) -> dict[Any, float]:
    return {(r["case_id"], r["rep"]): _s(r, score) for r in rows}


def _seq(r: dict[str, Any]) -> tuple[str, ...]:
    return tuple(c["name"] for c in business_calls(r))


def _loads(r: dict[str, Any]) -> int:
    return sum(1 for c in r.get("calls") or [] if c["name"] == "load_skill")


def _exposed_ok(r: dict[str, Any]) -> bool | None:
    """An acceptable business tool is among the tools exposed to the executor (None when
    the gold is abstention only)."""
    acc = [t for t in r["expected"].get("acceptable_tools") or [] if t != ABSTAIN]
    if not acc:
        return None
    return any(t in (r.get("exposed_tools") or []) for t in acc)


# ------------------------------------------------------------------ 1. D-002 comparison


def _row_metrics(rs: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {
        s: ci_json(bootstrap_mean(by_case(rs, lambda r, s=s: itt(r, s)))) for s, _ in PARTS
    }

    def cost(field: str) -> Callable[[dict[str, Any]], float | None]:
        return lambda r: (r.get("cost_usd") or {}).get(field)

    def tok(field: str) -> Callable[[dict[str, Any]], float | None]:
        return lambda r: (r.get("tokens") or {}).get(field)

    out |= {
        "cost_turn": ci_json(bootstrap_mean(by_case(rs, cost("total")))),
        "cost_routing": ci_json(bootstrap_mean(by_case(rs, cost("routing")))),
        "cost_executor": ci_json(bootstrap_mean(by_case(rs, cost("agent")))),
        "prompt_tokens": ci_json(bootstrap_mean(by_case(rs, tok("prompt")))),
        "completion_tokens": ci_json(bootstrap_mean(by_case(rs, tok("completion")))),
        "executor_calls": mean((r.get("tokens") or {}).get("agent_calls", 0) for r in rs),
        "exposed_tools": mean(len(r.get("exposed_tools") or []) for r in rs),
        "errors": sum(1 for r in rs if r.get("error")),
        "rows": len(rs),
        "loop_limit": sum(1 for r in rs if r.get("outcome") == "loop_limit"),
    }
    return out


def _contrast(a: list[dict[str, Any]], b: list[dict[str, Any]], score: str) -> dict[str, Any]:
    ka, kb = _keys(a, score), _keys(b, score)
    d = paired_delta(ka, kb)
    mc = mcnemar_cases(ka, kb)
    p = sign_flip(ka, kb)
    return {
        "delta": ci_json(d),
        "n": mc[0] if mc else 0,
        "a_only": mc[1] if mc else 0,
        "b_only": mc[2] if mc else 0,
        "mcnemar_p": mc[3] if mc else None,
        "sign_flip_p": p,
    }


def d002(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    runs: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for k in ("E0", "E9", "E7"):
        if k in ctx.e2e:
            runs[k] = (ctx.e2e_runs[k].label, ctx.e2e[k])
    for k, (name, label, _) in D002.items():
        rs = rows_of(name)
        if rs is not None:
            runs[k] = (label + " (D-002)", rs)
    js: dict[str, Any] = {"runs": {}, "contrasts": {}}
    lines = [
        "## 1. Deviation D-002: route the skill, expose all its tools (EXPLORATORY, post hoc)",
        "",
        "`x-e9-fullskill-e2e-r1` / `x-e7-fullskill-e2e-r1` = the frozen E9 / E7 configs with `routing.tool.expose_top_k: 5` "
        "(all 5 tools of the routed skill + the 3 global tools exposed to the Sonnet 5 executor) instead of the pre-registered top-2. "
        "Router decisions are response-cache hits of the same samples (paired by construction); only the executor is resampled. "
        "Designed AFTER seeing H3 on the same split: hypothesis-generating, not confirmatory; p-values unadjusted and descriptive.",
        "",
    ]
    if not all(k in runs for k in ("E0", "E9-full")):
        return lines + ["D-002 runs not complete.", ""], js
    # routing identical?
    for k, (_, _, base) in D002.items():
        if k in runs and base in runs:
            a = {r["case_id"]: (r.get("skill") or {}).get("choice") for r in runs[k][1]}
            b = {r["case_id"]: (r.get("skill") or {}).get("choice") for r in runs[base][1]}
            js.setdefault("same_skill_choice", {})[k] = sum(1 for c in a if c in b and a[c] == b[c])
    rows = []
    for k, (label, rs) in runs.items():
        m = _row_metrics(rs)
        js["runs"][k] = {"label": label} | m
        rows.append(
            [label, m["rows"], m["errors"]]
            + [fmt(tuple(m[s].values())) for s, _ in PARTS]
            + [f"{m['exposed_tools']:.2f}", m["loop_limit"]]
        )
    lines += ["### e2e scores (ITT, 1 rep, 349 cases; % [95% cluster-bootstrap CI])", ""]
    lines += md_table(
        ["run", "rows", "errors"]
        + [lab for _, lab in PARTS]
        + ["tools exposed/turn (mean)", "loop_limit turns"],
        rows,
    )
    same = js.get("same_skill_choice", {})
    lines += [
        "Routed skill identical to the top-2 run in "
        + ", ".join(f"{k} {v}/349" for k, v in same.items())
        + " cases (same cached router samples).",
        "",
    ]
    pairs = [
        ("E9-full", "E9"),
        ("E9-full", "E0"),
        ("E7-full", "E7"),
        ("E7-full", "E0"),
        ("E9", "E0"),
        ("E7", "E0"),
    ]
    crow = []
    for a, b in pairs:
        if a not in runs or b not in runs:
            continue
        for score in ("e2e_success", "first_call_success", "tool_correct"):
            c = _contrast(runs[a][1], runs[b][1], score)
            js["contrasts"][f"{a}-{b}:{score}"] = c
            crow.append(
                [
                    f"{a} - {b}",
                    score,
                    c["n"],
                    fmt(tuple(c["delta"].values())) if c["delta"] else "-",
                    f"{c['a_only']}/{c['b_only']}",
                    f"{c['mcnemar_p']:.3g}" if c["mcnemar_p"] is not None else "-",
                    f"{c['sign_flip_p']:.3g}" if c["sign_flip_p"] is not None else "-",
                ]
            )
    lines += [
        "### Paired contrasts (EXPLORATORY; unadjusted)",
        "",
        "E9 - E0 is the pre-registered H3 contrast (primary.md), repeated here for reference.",
        "",
    ]
    lines += md_table(
        [
            "contrast",
            "score",
            "n cases",
            "Δ pp [95% CI] (paired cluster bootstrap)",
            "McNemar run-only/ref-only",
            "McNemar exact p",
            "sign-flip p",
        ],
        crow,
    )
    # cost / tokens
    cost_rows = []
    for k, (label, _) in runs.items():
        m = js["runs"][k]
        cost_rows.append(
            [
                label,
                fmt(tuple(m["cost_turn"].values()), 1000, 2),
                fmt(tuple(m["cost_routing"].values()), 1000, 2),
                fmt(tuple(m["cost_executor"].values()), 1000, 2),
                fmt(tuple(m["prompt_tokens"].values()), 1, 0),
                fmt(tuple(m["completion_tokens"].values()), 1, 0),
                f"{m['executor_calls']:.2f}",
            ]
        )
    lines += ["### Cost per turn and tokens (observed regime)", ""]
    lines += md_table(
        [
            "run",
            "US$/1k turns total [CI]",
            "routing [CI]",
            "executor [CI]",
            "executor prompt tokens/turn [CI]",
            "completion tokens/turn [CI]",
            "executor calls/turn",
        ],
        cost_rows,
    )
    ratio_rows = []
    for a, b in (("E9-full", "E0"), ("E9-full", "E9"), ("E7-full", "E0"), ("E7-full", "E7")):
        if a not in runs or b not in runs:
            continue
        for field, lab in (("total", "US$/turn"), ("prompt", "prompt tokens/turn")):

            def val(r: dict[str, Any], field: str = field) -> float | None:
                src = r.get("cost_usd") if field == "total" else r.get("tokens")
                return (src or {}).get(field)

            rr = paired_ratio(by_case(runs[a][1], val), by_case(runs[b][1], val))
            if rr:
                js["contrasts"][f"{a}/{b}:{field}"] = {
                    "ratio": rr[0],
                    "lo": rr[1],
                    "hi": rr[2],
                    "n": rr[3],
                }
                ratio_rows.append(
                    [f"{a} / {b}", lab, rr[3], f"{rr[0]:.3f} [{rr[1]:.3f}, {rr[2]:.3f}]"]
                )
    lines += ["Paired ratios of means (cluster bootstrap):", ""]
    lines += md_table(["ratio", "quantity", "n cases", "ratio [95% CI]"], ratio_rows)
    return lines, js


# ------------------------------------------------------------------ 2. error analysis

ROUTED_LOSS = (
    (
        "A1",
        "routed skill label not accepted, executor behaviour identical to native (same business calls) - out-of-scope gold",
    ),
    (
        "A2",
        "routed skill label not accepted, executor behaviour identical to native (same business calls) - in-scope gold",
    ),
    ("B", "routed skill wrong and the executor acted differently (routing error changed the turn)"),
    ("C", "routed skill right, but no acceptable tool exposed to the executor"),
    ("D", "native credited by a clarification question; routed executor did not ask it"),
    ("E", "native recovered with a later call; routed did not"),
    ("F", "acceptable tool exposed; routed executor's first business call differs from native's"),
    ("G", "same first business call as native, but routed args invalid / call not finished"),
    ("Z", "other"),
)
NATIVE_LOSS = (
    ("N1", "native answered without any business call; routed executor acted (and succeeded)"),
    ("N2", "native loaded a wrong skill first"),
    ("N3", "native hit the loop limit"),
    ("N4", "same first business call, native args invalid / call not finished"),
    ("N5", "native first business call differs from routed (other)"),
    ("Z", "other"),
)


def _routed_loss(rt: dict[str, Any], nt: dict[str, Any]) -> str:
    """Why the routed turn failed where native succeeded (first matching rule)."""
    skill_ok = _s(rt, "skill_correct") >= 0.5
    same = _seq(rt) == _seq(nt)
    if not skill_ok and same:
        out_scope = ABSTAIN in (rt["expected"].get("acceptable_skills") or [])
        return "A1" if out_scope else "A2"
    if not skill_ok:
        return "B"
    if _exposed_ok(rt) is False:
        return "C"
    if _s(nt, "clarification_credited") >= 0.5:
        return "D"
    if _s(nt, "recovered_credited") >= 0.5:
        return "E"
    if (_seq(rt)[:1] or (ABSTAIN,)) != (_seq(nt)[:1] or (ABSTAIN,)):
        return "F"
    if _seq(rt)[:1] == _seq(nt)[:1]:
        return "G"
    return "Z"


def _native_loss(rt: dict[str, Any], nt: dict[str, Any]) -> str:
    if not _seq(nt):
        return "N1"
    if _s(nt, "skill_correct") < 0.5:
        return "N3" if nt.get("outcome") == "loop_limit" else "N2"
    if nt.get("outcome") == "loop_limit":
        return "N3"
    if _seq(rt)[:1] == _seq(nt)[:1]:
        return "N4"
    return "N5"


def error_analysis(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    lines = [
        "## 2. Why is routed e2e below native E0? Discordant-case error analysis (EXPLORATORY)",
        "",
        "Unit: case (1 rep each). A discordant case succeeds (e2e_success) in exactly one of the two runs. Each one gets ONE class, "
        "by the first matching rule in the order listed. `business calls` = the MCP tool calls the server executed (no `load_skill`). "
        "`native >1 load_skill` counts the discordant cases where E0 loaded two skills (switched skill) in that turn. Classes are "
        "mechanical (from the recorded rows), not a human judgement of the transcripts.",
        "",
        "Scoring note (class A): in a routed run the e2e skill is the ROUTER's skill label; in E0 it is the first skill the agent "
        "loads (`__abstain__` when it made no call, `__global__` when it only used global tools; docs/metrics.md). So a routed turn "
        "whose executor did exactly what the native agent did (e.g. declined an out-of-scope request without any call, or called "
        "the global `search_help_center`) still fails when the router labelled a wrong skill (e.g. `__global__` instead of "
        "`__abstain__`). This is the pre-registered scorer and is NOT changed here; class A only measures how much of the gap it explains.",
        "",
    ]
    e0 = {r["case_id"]: r for r in ctx.e2e.get("E0", [])}
    if not e0:
        return lines + ["E0 not available.", ""], js
    comps = [("E9", ctx.e2e.get("E9"))]
    full = rows_of(D002["E9-full"][0])
    if full is not None:
        comps.append(("E9-full", full))
    full7 = rows_of(D002["E7-full"][0])
    if "E7" in ctx.e2e:
        comps.append(("E7", ctx.e2e["E7"]))
    if full7 is not None:
        comps.append(("E7-full", full7))
    for key, rows in comps:
        if not rows:
            continue
        rt = {r["case_id"]: r for r in rows}
        shared = sorted(set(rt) & set(e0))
        n_only = [c for c in shared if _s(e0[c], "e2e_success") >= 0.5 > _s(rt[c], "e2e_success")]
        r_only = [c for c in shared if _s(rt[c], "e2e_success") >= 0.5 > _s(e0[c], "e2e_success")]
        loss = Counter(_routed_loss(rt[c], e0[c]) for c in n_only)
        gain = Counter(_native_loss(rt[c], e0[c]) for c in r_only)
        multi_n = sum(1 for c in n_only if _loads(e0[c]) > 1)
        multi_r = sum(1 for c in r_only if _loads(e0[c]) > 1)
        cat = Counter(e0[c]["category"] for c in n_only)
        examples = {k: [c for c in n_only if _routed_loss(rt[c], e0[c]) == k][:4] for k in loss}
        rescued: dict[str, Any] = {}
        if key == "E9" and full is not None:
            fx = {r["case_id"]: r for r in full}
            for k in loss:
                cs = [c for c in n_only if _routed_loss(rt[c], e0[c]) == k]
                rescued[k] = [sum(1 for c in cs if _s(fx[c], "e2e_success") >= 0.5), len(cs)]
        js[key] = {
            "n_cases": len(shared),
            "native_only": len(n_only),
            "routed_only": len(r_only),
            "routed_loss_classes": dict(loss),
            "native_loss_classes": dict(gain),
            "native_multi_load_in_native_only": multi_n,
            "native_multi_load_in_routed_only": multi_r,
            "native_only_by_category": dict(cat),
            "examples": examples,
            "rescued_by_full_skill": rescued,
        }
        label = {
            "E9": "E9 (top-2 tools, pre-registered) vs E0",
            "E9-full": "E9 all skill tools exposed (D-002) vs E0",
            "E7": "E7 (top-2) vs E0",
            "E7-full": "E7 all skill tools exposed (D-002) vs E0",
        }[key]
        lines += [
            f"### {label}",
            "",
            f"Cases {len(shared)}; native-only successes **{len(n_only)}**, routed-only successes **{len(r_only)}** "
            f"(net {len(r_only) - len(n_only):+d} cases = {100 * (len(r_only) - len(n_only)) / len(shared):+.1f} pp). "
            f"Native-only by category: {', '.join(f'{k} {v}' for k, v in cat.most_common())}.",
            "",
        ]
        rows_md = []
        for k, desc in ROUTED_LOSS:
            if loss.get(k):
                extra = [f"{rescued[k][0]}/{rescued[k][1]}"] if rescued else []
                rows_md.append(
                    [k, desc, loss[k], f"{100 * loss[k] / len(n_only):.0f}%"]
                    + extra
                    + [", ".join(examples[k])]
                )
        lines += [f"Native succeeded, {key} failed ({len(n_only)} cases):", ""]
        lines += md_table(
            ["class", "why the routed turn failed", "cases", "share"]
            + (["succeeds in E9-full (D-002)"] if rescued else [])
            + ["examples"],
            rows_md,
        )
        # post-hoc sensitivity: class A turns scored like native (behaviour-based skill)
        a_cases = {c for c in n_only if _routed_loss(rt[c], e0[c]) in ("A1", "A2")}
        adj = {(c, 1): (1.0 if c in a_cases else _s(rt[c], "e2e_success")) for c in shared}
        ref = {(c, 1): _s(e0[c], "e2e_success") for c in shared}
        d_adj = paired_delta(adj, ref)
        js[key]["label_agnostic_sensitivity"] = {
            "n_reclassified": len(a_cases),
            "routed_e2e": mean(adj.values()),
            "delta_vs_e0": ci_json(d_adj),
        }
        lines += [
            f"Post-hoc sensitivity (NOT the pre-registered scorer): if the {len(a_cases)} class-A turns were scored by behaviour "
            f"like native, {key} e2e_success would be {100 * mean(adj.values()):.1f}% and {key} - E0 = {fmt(d_adj)} pp.",
            "",
        ]
        rows_g = [
            [k, desc, gain[k], f"{100 * gain[k] / max(1, len(r_only)):.0f}%"]
            for k, desc in NATIVE_LOSS
            if gain.get(k)
        ]
        lines += [f"{key} succeeded, native failed ({len(r_only)} cases):", ""]
        lines += md_table(["class", "why native failed", "cases", "share"], rows_g)
        lines += [
            f"Native loaded two skills (`load_skill` twice) in {multi_n} of the native-only and {multi_r} of the routed-only cases.",
            "",
        ]
    # native multi-skill behaviour overall
    multi = [r for r in e0.values() if _loads(r) > 1]
    none = [r for r in e0.values() if _loads(r) == 0]
    js["native_load_skill"] = {
        "twice": len(multi),
        "twice_success": sum(_s(r, "e2e_success") for r in multi),
        "once": sum(1 for r in e0.values() if _loads(r) == 1),
        "never": len(none),
        "never_success": sum(_s(r, "e2e_success") for r in none),
    }
    nl = js["native_load_skill"]
    lines += [
        "### Native E0 skill loading (all 349 cases)",
        "",
        f"`load_skill` called once in {nl['once']} turns, twice in {nl['twice']} (e2e_success {int(nl['twice_success'])}/{nl['twice']}), "
        f"never in {nl['never']} (global tools or no call; e2e_success {int(nl['never_success'])}/{nl['never']}).",
        "",
    ]
    return lines, js


# ------------------------------------------------------------------ 3. routing confusions

CONFUSION_RUNS = ("E1", "E3", "E10", "E6b", "E4", "E5", "E9")


def confusions(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    """Most frequent (gold first-listed tool -> predicted tool) errors, routing-only, rep 1."""
    js: dict[str, Any] = {}
    lines = [
        "## 3. Confusable pairs in routing-only (descriptive)",
        "",
        "Rep 1 of each run (349 cases), joint-wrong rows only: gold = first-listed acceptable tool (`__abstain__` for "
        "out-of-scope), predicted = the router's top-1 tool (`__abstain__` when it abstained; skill-wrong rows included). "
        "Multi-label cases count only when no acceptable label was predicted. `[skill X]` = the tool was acceptable but the "
        "routed skill X was not (a skill-stage error). Top 6 pairs per router.",
        "",
    ]
    rows_md = []
    for k in CONFUSION_RUNS:
        rs = [r for r in ctx.routing.get(k, []) if r.get("rep", 1) == 1]
        if not rs:
            continue
        cnt: Counter[tuple[str, str]] = Counter()
        for r in rs:
            if _s(r, "joint_correct") >= 0.5:
                continue
            gold = (r["expected"].get("acceptable_tools") or [ABSTAIN])[0]
            tool = r.get("tool") or {}
            pred = ABSTAIN if r.get("error") else (tool.get("choice") or ABSTAIN)
            if tool.get("abstained"):
                pred = ABSTAIN
            acc = r["expected"].get("acceptable_tools") or []
            if pred in acc or (pred == "escalate_to_human" and ABSTAIN in acc):
                skill = r.get("skill") or {}
                pred = f"{pred} [skill {skill.get('choice') or ABSTAIN}]"
            cnt[(gold, pred)] += 1
        js[k] = {f"{g} -> {p}": n for (g, p), n in cnt.most_common(10)}
        wrong = sum(cnt.values())
        rows_md.append(
            [
                ctx.runs[k].label,
                wrong,
                "; ".join(f"{g} -> {p} ({n})" for (g, p), n in cnt.most_common(6)),
            ]
        )
    lines += md_table(
        ["router", "joint-wrong cases (rep 1)", "top confusions: gold -> predicted (n)"], rows_md
    )
    return lines, js


def run_exploratory(ctx: Context) -> dict[str, Any]:
    lines = [
        "# Exploratory end-to-end analyses (test-v2; post hoc, NOT confirmatory)",
        "",
        "Generated by `scripts/analysis/final_all.py` (module `final_exploratory.py`) from `results/rescored/`. ITT; paired cluster "
        "bootstrap over case ids, 10k resamples, seed 20260930. Every result here was designed after the pre-registered "
        "results were seen (deviation D-002) and uses the same test split: hypothesis-generating only.",
        "",
    ]
    out: dict[str, Any] = {}
    for name, fn in (
        ("d002", d002),
        ("error_analysis", error_analysis),
        ("confusions", confusions),
    ):
        md, js = fn(ctx)
        lines += md
        out[name] = js
    write(OUT / "exploratory_e2e.md", "\n".join(lines))
    write_json(OUT / "exploratory_e2e.json", out)
    return out


def run_exploratory_figures(js: dict[str, Any]) -> list[str]:
    """final-x-d002-e2e.png and final-x-e2e-error-classes.png (matplotlib)."""
    import matplotlib.pyplot as plt
    import numpy as np
    from final_common import SURFACE, TEXT
    from final_figures import SERIES4, _save

    out: list[str] = []
    runs = (js.get("d002") or {}).get("runs") or {}
    order = [k for k in ("E0", "E9", "E9-full", "E7", "E7-full") if k in runs]
    if order:
        parts = (
            ("first_call_success", "first call"),
            ("clarification_credited", "clarification credited"),
            ("recovered_credited", "recovered"),
        )
        fig, ax = plt.subplots(figsize=(7.5, 3.8))
        left = np.zeros(len(order))
        for (s, lab), color in zip(parts, SERIES4, strict=False):
            vals = np.array([100 * runs[k][s]["point"] for k in order])
            ax.barh(
                range(len(order)),
                vals,
                left=left,
                color=color,
                label=lab,
                edgecolor=SURFACE,
                linewidth=2,
                height=0.6,
            )
            left += vals
        for i, k in enumerate(order):
            ci = runs[k]["e2e_success"]
            ax.errorbar(
                100 * ci["point"],
                i,
                xerr=[[100 * (ci["point"] - ci["lo"])], [100 * (ci["hi"] - ci["point"])]],
                color=TEXT,
                capsize=3,
                lw=1,
            )
            ax.text(
                100 * ci["hi"] + 1,
                i,
                f"{100 * ci['point']:.1f}%  (US$ {1000 * runs[k]['cost_turn']['point']:.1f}/1k turns, "
                f"{runs[k]['exposed_tools']:.1f} tools)",
                va="center",
                fontsize=7.5,
            )
        names = {
            "E0": "E0 native (no router)",
            "E9": "E9 top-2 tools (prereg)",
            "E9-full": "E9 all skill tools (D-002)",
            "E7": "E7 top-2 tools (prereg)",
            "E7-full": "E7 all skill tools (D-002)",
        }
        ax.set_yticks(range(len(order)), [names[k] for k in order])
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.set_xlabel("e2e_success % (ITT; bars = disjoint parts, whisker = 95% CI of the total)")
        ax.set_title("EXPLORATORY D-002: exposing all tools of the routed skill")
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, fontsize=7.5)
        _save(fig, "final-x-d002-e2e.png", out)
    ea = js.get("error_analysis") or {}
    keys = [k for k in ("E9", "E9-full") if k in ea]
    if keys:
        classes = [
            k for k, _ in ROUTED_LOSS if any(ea[x]["routed_loss_classes"].get(k) for x in keys)
        ]
        short = {
            "A1": "A1 label only, out-of-scope",
            "A2": "A2 label only, in-scope",
            "B": "B wrong skill, behaviour changed",
            "C": "C tool not exposed",
            "D": "D native clarified",
            "E": "E native recovered",
            "F": "F different first call",
            "G": "G same call, bad args",
            "Z": "Z other",
        }
        fig, ax = plt.subplots(figsize=(7.5, 3.6))
        h = 0.38
        for j, (x, color) in enumerate(zip(keys, ("#4a3aa7", "#1baf7a"), strict=False)):
            vals = [ea[x]["routed_loss_classes"].get(k, 0) for k in classes]
            ys = np.arange(len(classes)) + (j - 0.5) * h
            ax.barh(
                ys,
                vals,
                height=h,
                color=color,
                label=f"{x} vs E0: native-only {ea[x]['native_only']}, routed-only {ea[x]['routed_only']}",
            )
            for y, v in zip(ys, vals, strict=True):
                if v:
                    ax.text(v + 0.3, y, str(v), va="center", fontsize=7.5)
        ax.set_yticks(range(len(classes)), [short[k] for k in classes])
        ax.invert_yaxis()
        ax.set_xlabel("discordant cases where native E0 succeeded and the routed run failed")
        ax.set_title("EXPLORATORY: why routed e2e loses to native E0")
        ax.legend(loc="lower right", fontsize=7.5)
        _save(fig, "final-x-e2e-error-classes.png", out)
    return out


__all__ = ["run_exploratory", "run_exploratory_figures"]
