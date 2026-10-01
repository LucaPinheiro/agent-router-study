# ruff: noqa: E501  (report prose and table rows)
"""Confirmatory (H1-H3, Holm) and secondary (S1-S4) analyses of prereg-v1 on test-v2.

Writes results/analysis/primary.{md,json} and results/analysis/secondary.{md,json}.
Tests and intervals are exactly `routing_study.eval.stats` (paired cluster bootstrap over case
ids, per-case means over reps, 10k resamples, seed 20260930; sign-flip p; Holm within family).
"""

from __future__ import annotations

from typing import Any

import yaml
from final_common import (
    DEV_FIXED,
    OUT,
    PROMPT_SELECTION,
    Context,
    by_case,
    ci_json,
    fmt,
    fnum,
    itt_keys,
    md_table,
    paired_ratio,
    write,
    write_json,
)

from routing_study.eval.report import itt
from routing_study.eval.stats import Contrast, bootstrap_mean, evaluate_contrasts

H_CONTRASTS = [
    ("H1", "E9", "E5", "routing", Contrast("E9", "E5", "H", "non_inferiority", 0.03)),
    ("H2", "E7", "E5", "routing", Contrast("E7", "E5", "H", "non_inferiority", 0.03)),
    ("H3", "E9", "E0", "e2e", Contrast("E9@e2e", "E0@e2e", "H", "two_sided")),
]
S2 = [("Haiku 4.5", "E6"), ("Qwen3-8B", "E6b"), ("Jev", "E4")]


def _scores(ctx: Context, error_free: bool = False) -> dict[str, dict[Any, float]]:
    """name -> (case, rep) -> ITT headline; with error_free, restricted to the case ids
    error-free in every run of its mode (sensitivity)."""
    out: dict[str, dict[Any, float]] = {}
    for _mode, runs, head, suffix in (
        ("routing", ctx.routing, "joint_correct", ""),
        ("e2e", ctx.e2e, "e2e_success", "@e2e"),
    ):
        keep: set[str] | None = None
        if error_free and runs:
            keep = set.intersection(
                *(
                    {r["case_id"] for r in rs} - {r["case_id"] for r in rs if r.get("error")}
                    for rs in runs.values()
                )
            )
        for k, rs in runs.items():
            rows = [r for r in rs if keep is None or r["case_id"] in keep]
            out[k + suffix] = itt_keys(rows, head)
    return out


def _pairwise_error_free(
    scores: dict[str, dict[Any, float]], ctx: Context, contrasts: list[Contrast]
) -> tuple[dict[str, dict[Any, float]], list[Contrast], list[int]]:
    """Sensitivity: each contrast restricted to the case ids error-free in BOTH of its runs
    (renamed copies so one Holm family can still be evaluated together)."""
    rows = {**ctx.routing, **{k + "@e2e": v for k, v in ctx.e2e.items()}}
    out: dict[str, dict[Any, float]] = {}
    new: list[Contrast] = []
    sizes: list[int] = []
    for i, c in enumerate(contrasts):
        if c.run not in rows or c.reference not in rows:
            new.append(c)
            sizes.append(0)
            continue
        bad = {r["case_id"] for k in (c.run, c.reference) for r in rows[k] if r.get("error")}
        keep = (
            {r["case_id"] for r in rows[c.run]} & {r["case_id"] for r in rows[c.reference]}
        ) - bad
        a, b = f"{c.run}#{i}", f"{c.reference}#{i}"
        out[a] = {k: v for k, v in scores[c.run].items() if k[0] in keep}
        out[b] = {k: v for k, v in scores[c.reference].items() if k[0] in keep}
        new.append(Contrast(a, b, c.family, c.kind, c.margin))
        sizes.append(len(keep))
    return out, new, sizes


def _verdict(res: dict[str, Any]) -> str:
    v = res.get("verdict") or {}
    if "non_inferior" in v:
        return (
            "non-inferior (CI lower bound > -3 pp)"
            if v["non_inferior"]
            else "non-inferiority NOT shown"
        )
    if "conclusion" in v:
        return v["conclusion"]
    lo, hi = res["delta_ci"][1], res["delta_ci"][2]
    return "CI excludes 0" if lo > 0 or hi < 0 else "CI includes 0 (no directional claim)"


def _contrast_rows(
    results: list[dict[str, Any]], names: list[str]
) -> tuple[list[list[Any]], list[dict[str, Any]]]:
    table, js = [], []
    for name, res in zip(names, results, strict=True):
        c = res["contrast"]
        if "missing" in res:
            table.append(
                [
                    name,
                    c.run,
                    c.reference,
                    c.kind,
                    "-",
                    f"missing run {res['missing']}",
                    "",
                    "",
                    "",
                    "",
                    "not run / not complete",
                ]
            )
            js.append({"id": name, "missing": res["missing"]})
            continue
        mc = res["mcnemar"]
        table.append(
            [
                name,
                c.run,
                c.reference,
                c.kind + (f" (margin {100 * c.margin:g} pp)" if c.kind != "two_sided" else ""),
                res["n_cases"],
                fmt(res["delta_ci"]),
                f"{mc[1]}/{mc[2]} p={mc[3]:.3g}" if mc else "-",
                f"{res['p']:.4g}" if res["p"] is not None else "-",
                f"{res.get('p_holm'):.4g}" if res.get("p_holm") is not None else "-",
                "yes" if res.get("reject") else "no",
                _verdict(res),
            ]
        )
        v = res.get("verdict") or {}
        js.append(
            {
                "id": name,
                "run": c.run,
                "reference": c.reference,
                "kind": c.kind,
                "margin": c.margin,
                "n_cases": res["n_cases"],
                "delta": ci_json(res["delta_ci"]),
                "mcnemar_case": {"run_only": mc[1], "ref_only": mc[2], "p": mc[3]} if mc else None,
                "p": res["p"],
                "p_holm": res.get("p_holm"),
                "reject_holm_0.05": res.get("reject"),
                "verdict": _verdict(res),
                "verdict_ci": {k: v[k] for k in ("lo", "hi") if k in v} or None,
            }
        )
    return table, js


def cost_ratio(
    ctx: Context, a: str, b: str, e2e: bool = False
) -> tuple[float, float, float, int] | None:
    runs = ctx.e2e if e2e else ctx.routing
    if a not in runs or b not in runs:
        return None
    field = "total" if e2e else "routing"
    va = by_case(runs[a], lambda r: (r.get("cost_usd") or {}).get(field))
    vb = by_case(runs[b], lambda r: (r.get("cost_usd") or {}).get(field))
    return paired_ratio(va, vb)


def run_primary(ctx: Context) -> dict[str, Any]:
    header = [
        "id",
        "run",
        "reference",
        "kind",
        "n cases",
        "Δ pp [95% CI] (paired cluster bootstrap)",
        "McNemar case-level run-only/ref-only",
        "sign-flip p",
        "Holm p (H1-H3)",
        "reject @0.05",
        "verdict",
    ]
    names = [h[0] for h in H_CONTRASTS]
    contrasts = [h[4] for h in H_CONTRASTS]
    out: dict[str, Any] = {"status": "CONFIRMATORY (prereg-v1, Holm across H1-H3, alpha 0.05)"}
    lines = [
        "# Primary analysis (confirmatory): prereg-v1 H1-H3 on test-v2",
        "",
        "Generated by `scripts/analysis/final_all.py` from `results/rescored/` (scorer e0eef1fb0073). "
        "Unit = case (reps averaged per case first); paired cluster bootstrap over case ids, 10 000 "
        "resamples, seed 20260930; p = case-level sign-flip (non-inferiority: shift +0.03, one-sided); "
        "Holm step-down across H1-H3. Intention to treat (ITT): an error row is wrong.",
        "",
    ]
    scores = _scores(ctx)
    for label, err_free in (
        ("ITT (primary)", False),
        ("error-free cases of both runs (sensitivity)", True),
    ):
        if err_free:
            sc, cs, sizes = _pairwise_error_free(scores, ctx, contrasts)
        else:
            sc, cs, sizes = scores, contrasts, []
        results = evaluate_contrasts(sc, cs)
        table, js = _contrast_rows(results, names)
        for row in table:
            row[1], row[2] = str(row[1]).split("#")[0], str(row[2]).split("#")[0]
        lines += [f"## Contrasts: {label}", ""] + md_table(header, table)
        out["itt" if not err_free else "error_free"] = js
        if err_free:
            lines += [
                "Cases error-free in both runs: "
                + ", ".join(f"{n} {s}" for n, s in zip(names, sizes, strict=True))
                + " (of 349).",
                "",
            ]
    # co-primary cost ratios
    lines += [
        "## Co-primary estimates: cost ratios (paired cluster bootstrap of the ratio of means)",
        "",
    ]
    crow = []
    for lab, a, b, e2e, what in (
        (
            "H1 co-primary",
            "E9",
            "E5",
            False,
            "routing US$/case, observed-cache regime (recorded cost of each decision)",
        ),
        ("H2 (estimation)", "E7", "E5", False, "routing US$/case, observed-cache regime"),
        ("H3 co-primary", "E9", "E0", True, "US$/turn, routing + executor, observed"),
    ):
        r = cost_ratio(ctx, a, b, e2e)
        runs = ctx.e2e if e2e else ctx.routing
        field = "total" if e2e else "routing"

        def per1k(k: str, runs: dict = runs, field: str = field) -> Any:
            return (
                bootstrap_mean(
                    by_case(runs[k], lambda row, f=field: (row.get("cost_usd") or {}).get(f))
                )
                if k in runs
                else None
            )

        ca, cb = per1k(a), per1k(b)
        crow.append(
            [
                lab,
                f"{a}/{b}",
                what,
                fmt(ca, 1000, 3),
                fmt(cb, 1000, 3),
                "-" if r is None else f"{r[0]:.3f} [{r[1]:.3f}, {r[2]:.3f}]",
                "-" if r is None else r[3],
                "-"
                if r is None
                else (
                    "< 0.5 (upper CI < 0.5)"
                    if r[2] < 0.5 and lab == "H1 co-primary"
                    else ("CI upper >= 0.5" if lab == "H1 co-primary" else "")
                ),
            ]
        )
        out.setdefault("cost_ratios", []).append(
            {
                "id": lab,
                "ratio": None
                if r is None
                else {"point": r[0], "lo": r[1], "hi": r[2], "n_cases": r[3]},
                "a_usd_per_1k": ci_json(None if ca is None else [1000 * x for x in ca]),
                "b_usd_per_1k": ci_json(None if cb is None else [1000 * x for x in cb]),
                "what": what,
            }
        )
    lines += md_table(
        [
            "estimate",
            "ratio",
            "what",
            "numerator US$/1k [95% CI]",
            "denominator US$/1k [95% CI]",
            "ratio [95% CI]",
            "n cases",
            "pre-registered target",
        ],
        crow,
    )
    # headline per-run numbers
    lines += ["## Headline per run (ITT, 95% cluster-bootstrap CI)", ""]
    hrow = []
    for k in ("E5", "E7", "E9"):
        if k in ctx.routing:
            rs = ctx.routing[k]
            hrow.append(
                [
                    ctx.runs[k].name,
                    "joint",
                    len(rs),
                    sum(1 for r in rs if r.get("error")),
                    fmt(bootstrap_mean(by_case(rs, lambda r: itt(r, "joint_correct")))),
                ]
            )
    for k in ("E0", "E9"):
        if k in ctx.e2e:
            rs = ctx.e2e[k]
            hrow.append(
                [
                    ctx.e2e_runs[k].name,
                    "e2e_success",
                    len(rs),
                    sum(1 for r in rs if r.get("error")),
                    fmt(bootstrap_mean(by_case(rs, lambda r: itt(r, "e2e_success")))),
                ]
            )
    lines += md_table(["run", "metric", "rows", "error rows", "% [95% CI]"], hrow)
    lines += [
        "## Reading",
        "",
        "- H1/H2 decision rule (pre-registered): non-inferior iff the lower bound of the two-sided 95% paired CI of Δ "
        "(= one-sided 97.5%) is above -3 pp. The Holm-adjusted sign-flip p tests H0: Δ <= -3 pp. The CI verdict "
        "and the Holm decision are both reported; when they disagree the CI rule is the pre-registered decision and the "
        "Holm column is the multiplicity-controlled test.",
        "- H3: two-sided; a directional claim only if the CI excludes 0.",
        "- E5 is the canonical Sonnet run; tuned == canonical (P0) for every LLM router, so it is also the tuned reference.",
        "- E9/E7/E5 routing-only reuse the same Sonnet/Jev samples of the shadow pass (response cache per case, rep, prompt): "
        "the pairing is by construction, and their recorded cost is the original (cache-independent) cost of each decision.",
        "",
    ]
    write(OUT / "primary.md", "\n".join(lines))
    write_json(OUT / "primary.json", out)
    return out


def _s1_dev() -> list[list[Any]]:
    data = yaml.safe_load(PROMPT_SELECTION.read_text(encoding="utf-8")) or {}
    rows = []
    for mid, m in (data.get("models") or {}).items():
        can, tun = m.get("canonical") or {}, m.get("tuned") or {}
        rows.append(
            [
                m.get("name", mid),
                can.get("variant"),
                tun.get("variant"),
                fnum(tun.get("nested_joint_mean")) + " ± " + fnum(tun.get("nested_joint_sd")),
                ", ".join(tun.get("nested_picks") or []) or "-",
                tun.get("raw_best") or "-",
            ]
        )
    return rows


def _errors_note(ctx: Context) -> str:
    parts = [
        f"{k} {sum(1 for r in rs if r.get('error'))}"
        for k, rs in ctx.routing.items()
        if any(r.get("error") for r in rs)
    ]
    return ("; ".join(parts) + " (all others 0)") if parts else "none in any run"


def run_secondary(ctx: Context) -> dict[str, Any]:
    out: dict[str, Any] = {}
    lines = [
        "# Secondary analyses (prereg-v1 S1-S4) on test-v2",
        "",
        "Same machinery as primary.md (paired cluster bootstrap, 10k, seed 20260930; sign-flip p; Holm within family). "
        "ITT (an error row is wrong). Error rows after rescore: " + _errors_note(ctx) + ".",
        "",
        "## S1 (prompt engineering, tuned - canonical): DEGENERATE by construction",
        "",
        "The pre-declared one-SE rule (5-fold CV on dev, ITT) selected P0 for both tracks of every LLM-type router, "
        "so tuned == canonical byte-for-byte and Δ ≡ 0: **no S1 test is run on test-v2** (pre-registered, not a dropped "
        "hypothesis). Finding: *the selection procedure found no prompt tuning worth applying*. Dev evidence "
        "(config/prompt_selection.yaml, docs/prompt-apex.md):",
        "",
    ]
    lines += md_table(
        [
            "model",
            "canonical",
            "tuned",
            "nested-CV joint % (tuned) mean ± SD",
            "nested outer-fold picks",
            "plain-argmax sensitivity (dev only)",
        ],
        _s1_dev(),
    )
    sel = yaml.safe_load(PROMPT_SELECTION.read_text(encoding="utf-8")) or {}
    cand = (sel.get("canonical") or {}).get("candidates") or {}
    lines += [
        "Over the four models the canonical candidates on full dev had mean CV joint "
        + ", ".join(f"{k} {100 * v:.1f}" for k, v in cand.items())
        + f" (one-SE rule kept {(sel.get('canonical') or {}).get('variant')}). "
        "The argmax alternatives are dev-only sensitivities and were not run on test-v2 (except Jev P0+P6c, exploratory cost variant; see estimation.md if complete).",
        "",
    ]
    out["S1"] = {
        "tested": False,
        "reason": "tuned == canonical (P0) for all 4 LLM routers; delta identically 0",
    }

    # S2 TOST
    scores = _scores(ctx)
    cs = [Contrast(k, "E5", "S2", "equivalence", 0.03) for _, k in S2]
    res = evaluate_contrasts(scores, cs)
    header = [
        "id",
        "run",
        "reference",
        "kind",
        "n cases",
        "Δ pp [95% CI]",
        "McNemar case-level",
        "TOST p (max of 2 one-sided)",
        "Holm p (S2)",
        "reject @0.05",
        "verdict (90% CI inside ±3 pp)",
    ]
    table, js = _contrast_rows(res, [f"S2 {n}" for n, _ in S2])
    # add the 90% CI used by the TOST verdict
    for row, r in zip(js, res, strict=True):
        if "verdict" in r:
            row["ci90"] = {"lo": r["verdict"]["lo"], "hi": r["verdict"]["hi"]}
    lines += [
        "## S2 (model vs model, canonical track): TOST ±3 pp vs Sonnet 5 (E5)",
        "",
    ] + md_table(header, table)
    lines += [
        "90% paired CIs used for the TOST verdict: "
        + "; ".join(
            f"{j['id']}: {100 * j['ci90']['lo']:.1f} to {100 * j['ci90']['hi']:.1f} pp"
            for j in js
            if j.get("ci90")
        )
        + ".",
        "",
    ]
    lines += [
        "Note: E6 Haiku and E6b Qwen have 1 rep, E5 has 3 (per-case means); the paired Δ is over the 349 shared cases.",
        "",
        "Reading: the pre-registered conclusion is the CI-inclusion rule on the unadjusted 90% paired CI. Under Holm within S2 "
        "(family-wise α 0.05) a pair is declared equivalent only if its TOST p, Holm-adjusted, is < 0.05. Where the two "
        "disagree (CI rule says equivalent, Holm p ≥ 0.05) the conservative reading is *equivalence not established after "
        "multiplicity control*; both are shown and neither is preferred post hoc.",
        "",
    ]
    if any(r.get("error") for r in ctx.routing.get("E4", [])):
        ef, cse, sizes = _pairwise_error_free(scores, ctx, cs)
        tef, _ = _contrast_rows(evaluate_contrasts(ef, cse), [f"S2 {n}" for n, _ in S2])
        for row in tef:
            row[1], row[2] = str(row[1]).split("#")[0], str(row[2]).split("#")[0]
        lines += [
            "S2 sensitivity: cases error-free in both runs ("
            + ", ".join(str(x) for x in sizes)
            + " cases)",
            "",
        ] + md_table(header, tef)
    out["S2"] = js

    # S3 generalisation
    s3rows, s3js = [], []
    for k, label in (("E1", "regex (rules written on dev)"), ("E2", "BM25 (dev fixed)")):
        if k not in ctx.routing:
            s3rows.append([label, "-", "-", "-", "missing"])
            continue
        ci = bootstrap_mean(by_case(ctx.routing[k], lambda r: itt(r, "joint_correct")))
        dev = DEV_FIXED[k]
        gap = (ci[0] - dev, ci[1] - dev, ci[2] - dev)
        verdict = (
            "gap < 0 (test CI entirely below dev)"
            if gap[2] < 0
            else ("gap > 0" if gap[1] > 0 else "CI includes 0")
        )
        s3rows.append([label, f"{100 * dev:.1f}", fmt(ci), fmt(gap), verdict])
        s3js.append(
            {
                "router": k,
                "dev_fixed": dev,
                "test": ci_json(ci),
                "gap": ci_json(gap),
                "verdict": verdict,
            }
        )
    lines += [
        "## S3 (dev -> test generalisation): test-v2 joint - dev CV joint",
        "",
        "Dev numbers are fixed by the pre-registration (regex 84.8 = dev joint of the rules written on dev; BM25 55.7 = dev fixed-config joint); "
        "the CI is the test-v2 cluster-bootstrap CI shifted by the fixed dev value (dev uncertainty ignored, as pre-registered). "
        "Hypothesis: regex gap < 0.",
        "",
    ]
    lines += md_table(
        ["router", "dev joint %", "test-v2 joint % [95% CI]", "gap pp [95% CI]", "verdict"], s3rows
    )
    out["S3"] = s3js

    # S4
    res4 = evaluate_contrasts(scores, [Contrast("E3", "E1", "S4", "two_sided")])
    table4, js4 = _contrast_rows(res4, ["S4 embedding - regex"])
    lines += ["## S4 (lexical vs semantic): E3 embedding - E1 regex, two-sided", ""] + md_table(
        header[:7] + ["sign-flip p", "Holm p (S4, 1 test)", "reject @0.05", "verdict"], table4
    )
    out["S4"] = js4
    write(OUT / "secondary.md", "\n".join(lines))
    write_json(OUT / "secondary.json", out)
    return out
