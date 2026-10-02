# ruff: noqa: E501  (report prose and table rows)
"""EXPLORATORY re-estimate of phase-1 H3 and every e2e arm under the symmetric scorer (plan T1.2).

uv run study rescore results/<each phase-1 e2e run>.jsonl --scorer sym   # -> results/rescored-sym/
uv run python scripts/analysis/phase1_sym.py

Reads `results/rescored/` (legacy scorer of record, e0eef1fb0073) and `results/rescored-sym/`
(`eval/scorers_sym.py`). Writes `docs/results/phase1-sym/exploratory_e2e_sym.{md,json}`. Offline,
zero API cost, deterministic: same statistics as primary.md (per-case means, paired cluster
bootstrap over case ids, 10k resamples, seed 20260930, exact McNemar on case majorities,
sign-flip p). Every number is EXPLORATORY: the symmetric scorer was designed after the phase-1
test-v2 results were seen. The confirmatory phase-1 verdict (legacy scorer) is not changed.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from final_common import ROOT, ci_json, fmt, md_table, write, write_json

from routing_study.eval.report import itt
from routing_study.eval.rescore import read_rescored
from routing_study.eval.scorers import business_calls
from routing_study.eval.stats import (
    BOOT_N,
    BOOT_SEED,
    bootstrap_mean,
    mcnemar_cases,
    paired_delta,
    sign_flip,
)

LEGACY_DIR = ROOT / "results" / "rescored"
SYM_DIR = ROOT / "results" / "rescored-sym"
OUT = ROOT / "docs" / "results" / "phase1-sym"
# phase-1 primary.md H3 (legacy scorer): the script refuses to write if it does not reproduce
H3_LEGACY = "-9.7 [-13.5, -6.0]"

ARMS = [  # key, run name, label
    ("E0", "v2-e0-native-e2e-r1", "E0 native (no router)"),
    ("E1", "v2-e1-regex-e2e-r1", "E1 regex"),
    ("E5", "v2-e5-sonnet-canonical-e2e-r1", "E5 Sonnet 5"),
    ("E6b", "v2-e6b-qwen-canonical-e2e-r1", "E6b Qwen3-8B local"),
    ("E7", "v2-e7-tuned-e2e-r1", "E7 regex->Jev"),
    ("E9", "v2-e9-tuned-e2e-r1", "E9 regex->Jev->Sonnet"),
    ("E11", "v2-e11-hybrid-e2e-r1", "E11 hybrid"),
    ("E9-full", "x-e9-fullskill-e2e-r1", "E9 all skill tools (D-002)"),
    ("E7-full", "x-e7-fullskill-e2e-r1", "E7 all skill tools (D-002)"),
]
VARIANCE = [  # executor rep2 on 60 cases (same routing, executor resampled)
    ("E0 rep2-60", "v2-e0-native-e2e-rep2-60"),
    ("E9 rep2-60", "v2-e9-tuned-e2e-rep2-60"),
]
CONTRASTS = [  # (id, run, reference)
    ("H3", "E9", "E0"),
    ("", "E1", "E0"),
    ("", "E5", "E0"),
    ("", "E6b", "E0"),
    ("", "E7", "E0"),
    ("", "E11", "E0"),
    ("D-002", "E9-full", "E0"),
    ("D-002", "E7-full", "E0"),
    ("D-002", "E9-full", "E9"),
    ("D-002", "E7-full", "E7"),
]
DECOMP = ("first_call_success", "clarification_credited", "recovered_credited")


def load(directory: Path, name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return read_rescored(directory / f"{name}.jsonl")


def keys(rows: list[dict[str, Any]], score: str) -> dict[Any, float]:
    return {(r["case_id"], r["rep"]): v for r in rows if (v := itt(r, score)) is not None}


def mean_ci(rows: list[dict[str, Any]], score: str) -> tuple[float, float, float] | None:
    groups: dict[str, list[float]] = {}
    for r in rows:
        v = itt(r, score)
        if v is not None:
            groups.setdefault(r["case_id"], []).append(v)
    return bootstrap_mean(groups)


def pct(rows: list[dict[str, Any]], score: str) -> str:
    vals = [v for r in rows if (v := itt(r, score)) is not None]
    return f"{100 * sum(vals) / len(vals):.1f}" if vals else "-"


def contrast(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> dict[str, Any]:
    ka, kb = keys(a, "e2e_success"), keys(b, "e2e_success")
    mc = mcnemar_cases(ka, kb)
    return {
        "delta": paired_delta(ka, kb),
        "mcnemar": mc,
        "p_sign_flip": sign_flip(ka, kb),
    }


def seq(r: dict[str, Any]) -> tuple[str, ...]:
    return tuple(c["name"] for c in business_calls(r))


def same_calls(
    run: list[dict[str, Any]], ref: list[dict[str, Any]], score: Callable[[dict[str, Any]], float]
) -> dict[str, int]:
    """Discordant cases (success in exactly one run) and how many of them have the SAME
    sequence of executed business calls in both runs."""
    a = {r["case_id"]: r for r in run}
    b = {r["case_id"]: r for r in ref}
    out = {"discordant": 0, "discordant_same_calls": 0, "ref_only": 0, "ref_only_same_calls": 0}
    for c in sorted(a.keys() & b.keys()):
        sa, sb = score(a[c]) >= 0.5, score(b[c]) >= 0.5
        if sa == sb:
            continue
        same = seq(a[c]) == seq(b[c])
        out["discordant"] += 1
        out["discordant_same_calls"] += same
        if sb:
            out["ref_only"] += 1
            out["ref_only_same_calls"] += same
    return out


def main() -> None:
    legacy: dict[str, list[dict[str, Any]]] = {}
    sym: dict[str, list[dict[str, Any]]] = {}
    sources: list[list[Any]] = []
    sym_hash: set[str] = set()
    for key, name, _ in ARMS + [(k, n, k) for k, n in VARIANCE]:
        pl, legacy[key] = load(LEGACY_DIR, name)
        ps, sym[key] = load(SYM_DIR, name)
        if ps.get("scorer") != "sym" or pl.get("scorer") is not None:
            raise SystemExit(
                f"{name}: rescored-sym must be the sym scorer and rescored the legacy one"
            )
        if ps["source"]["sha256"] != pl["source"]["sha256"]:
            raise SystemExit(f"{name}: legacy and sym were rescored from different raw files")
        sym_hash.add(ps["scorer_hash"])
        sources.append(
            [
                name,
                ps["source"]["rows"],
                ps["source"]["sha256"][:12],
                pl["scorer_hash"],
                ps["scorer_hash"],
            ]
        )
    js: dict[str, Any] = {
        "status": "EXPLORATORY (post hoc; symmetric scorer designed after the phase-1 test-v2 results)",
        "bootstrap": {"resamples": BOOT_N, "seed": BOOT_SEED, "unit": "case"},
        "scorer_sym_hash": sorted(sym_hash),
        "arms": {},
        "contrasts": {},
        "same_calls": {},
        "variance": {},
    }
    h3_legacy = fmt(contrast(legacy["E9"], legacy["E0"])["delta"]).replace("−", "-")
    if h3_legacy != H3_LEGACY:
        raise SystemExit(f"legacy H3 {h3_legacy} does not reproduce primary.md {H3_LEGACY}")

    lines = [
        "# Phase-1 e2e under the symmetric scorer (EXPLORATORY)",
        "",
        "**Every number on this page is EXPLORATORY.** The symmetric scorer (`src/routing_study/eval/scorers_sym.py`, "
        "prereg-v2 §4) was designed after the phase-1 test-v2 results were seen (the 22/40 same-calls finding in "
        "`exploratory_e2e.md` §2). It is re-applied here OFFLINE to the recorded phase-1 rows, at zero API cost. The "
        "confirmatory phase-1 verdict (prereg-v1 H3, legacy scorer `e0eef1fb0073`) is **not** changed: E0 > E9.",
        "",
        "What changes: the legacy scorer takes the e2e skill from the ROUTER's label in routed runs and from behaviour "
        "(`load_skill`) in E0. The symmetric scorer takes it from behaviour in both arms: the skill of the first "
        "skill-bound business tool the server executed; with no call, the skill of the tool credited by a clarification "
        "(inferred from the question, never from the router's tool); escalation-only or host abstention = `__abstain__`; "
        "only global calls = `__global__`; no action = `__abstain__`. It never reads `native`, the router's skill/tool "
        "or `resolved_by`. Everything else (args, completion, recovery, decomposition) is the legacy code.",
        "",
        f"Statistics: identical to primary.md. Unit = case (reps averaged first); paired cluster bootstrap over case ids, "
        f"{BOOT_N} resamples, seed {BOOT_SEED}; exact McNemar on per-case majorities; two-sided sign-flip p, **unadjusted**. "
        "Intention to treat (no e2e run had an error row). Legacy numbers are read from `results/rescored/`, symmetric "
        "ones from `results/rescored-sym/`, both rescored from the same raw files (sha256 checked).",
        "",
        "## 1. H3 (E9 − E0) under both scorers",
        "",
    ]
    h3 = {}
    for lab, src in (
        ("legacy (pre-registered, confirmatory in phase 1)", legacy),
        ("symmetric (EXPLORATORY)", sym),
    ):
        c = contrast(src["E9"], src["E0"])
        h3[lab] = c
    rows_h3 = []
    for lab, c in h3.items():
        src = legacy if lab.startswith("legacy") else sym
        mc = c["mcnemar"]
        rows_h3.append(
            [
                lab,
                fmt(mean_ci(src["E9"], "e2e_success")),
                fmt(mean_ci(src["E0"], "e2e_success")),
                f"**{fmt(c['delta'])}**",
                f"{mc[1]} / {mc[2]} (p={mc[3]:.3g})",
                f"{c['p_sign_flip']:.4g}",
            ]
        )
    lines += md_table(
        [
            "scorer",
            "E9 e2e_success % [95% CI]",
            "E0 e2e_success % [95% CI]",
            "Δ E9 − E0 pp [95% CI]",
            "McNemar E9-only / E0-only",
            "sign-flip p (unadjusted)",
        ],
        rows_h3,
    )
    lo, hi = h3["symmetric (EXPLORATORY)"]["delta"][1:]
    verdict = "the CI excludes 0" if lo > 0 or hi < 0 else "the CI includes 0"
    lines += [
        f"Legacy reproduces primary.md exactly ({H3_LEGACY}). Under the symmetric scorer, {verdict}.",
        "",
    ]
    js["h3"] = {
        lab: {
            "delta": ci_json(c["delta"]),
            "mcnemar_case": {
                "run_only": c["mcnemar"][1],
                "ref_only": c["mcnemar"][2],
                "p": c["mcnemar"][3],
            },
            "p_sign_flip_unadjusted": c["p_sign_flip"],
        }
        for lab, c in h3.items()
    }

    lines += ["## 2. Every e2e arm", "", "test-v2, 349 cases, 1 rep each.", ""]
    arm_rows = []
    downs = 0
    for key, _name, label in ARMS:
        lg, sy = mean_ci(legacy[key], "e2e_success"), mean_ci(sym[key], "e2e_success")
        pairs = [
            (itt(a, "e2e_success"), itt(b, "e2e_success"))
            for a, b in zip(legacy[key], sym[key], strict=True)
        ]
        up = sum(1 for a, b in pairs if a == 0.0 and b == 1.0)
        down = sum(1 for a, b in pairs if a == 1.0 and b == 0.0)
        flips = up + down
        downs += down
        arm_rows.append(
            [
                label,
                len(sym[key]),
                fmt(lg),
                f"**{fmt(sy)}**",
                f"{100 * (sy[0] - lg[0]):+.1f}",
                f"+{up} / −{down}",
            ]
            + [pct(sym[key], d) for d in DECOMP]
            + [pct(sym[key], "skill_correct")]
        )
        js["arms"][key] = {
            "n": len(sym[key]),
            "legacy": ci_json(lg),
            "sym": ci_json(sy),
            "rows_changed": flips,
            "fail_to_success": up,
            "success_to_fail": down,
            **{f"sym_{d}": float(pct(sym[key], d)) / 100 for d in DECOMP},
        }
    lines += md_table(
        [
            "arm",
            "n",
            "legacy e2e % [CI]",
            "sym e2e % [CI]",
            "sym − legacy pp",
            "rows changed",
            "sym: 1st call",
            "sym: + clarification",
            "sym: + recovery",
            "sym skill_correct %",
        ],
        arm_rows,
    )
    lines += [
        "`rows changed` = turns whose e2e verdict differs between the two scorers: +failure→success / −success→failure. "
        + (
            "In every arm the symmetric scorer only turns failures into successes, never the reverse."
            if downs == 0
            else f"{downs} turns in total go from success to failure."
        ),
        "",
        "## 3. Contrasts (paired, unadjusted, EXPLORATORY)",
        "",
    ]
    c_rows = []
    for cid, a, b in CONTRASTS:
        row = [cid, f"{a} − {b}"]
        for src, tag in ((legacy, "legacy"), (sym, "sym")):
            c = contrast(src[a], src[b])
            mc = c["mcnemar"]
            row += [fmt(c["delta"]), f"{mc[1]} / {mc[2]}"]
            js["contrasts"].setdefault(f"{a}-{b}", {})[tag] = {
                "delta": ci_json(c["delta"]),
                "run_only": mc[1],
                "ref_only": mc[2],
                "mcnemar_p": mc[3],
                "p_sign_flip_unadjusted": c["p_sign_flip"],
            }
        sym_d = js["contrasts"][f"{a}-{b}"]["sym"]["delta"]
        row.append("excludes 0" if sym_d["lo"] > 0 or sym_d["hi"] < 0 else "includes 0")
        c_rows.append(row)
    lines += md_table(
        [
            "",
            "contrast",
            "legacy Δ pp [95% CI]",
            "legacy run-only / ref-only",
            "sym Δ pp [95% CI]",
            "sym run-only / ref-only",
            "sym CI",
        ],
        c_rows,
    )

    lines += [
        "## 4. Same calls, different verdict",
        "",
        "Discordant cases (e2e success in exactly one of the two runs), and how many of them have the SAME sequence of "
        "executed business calls (no `load_skill`) in both runs. Phase 1 reported 22 of the 40 E0-only cases of E9 − E0 as "
        "classes A1 + A2 (same calls AND the router's skill label not accepted; `exploratory_e2e.md` §2). The legacy count here "
        "is a little larger because it also includes same-calls cases that failed on args or completion. A remaining same-calls "
        "discordance under the symmetric scorer comes from the args or the reply (e.g. a clarification), not from the skill label.",
        "",
    ]
    s_rows = []
    for _cid, a, b in CONTRASTS:
        if b != "E0":
            continue
        row = [f"{a} vs E0"]
        for src, tag in ((legacy, "legacy"), (sym, "sym")):
            sc = same_calls(src[a], src["E0"], lambda r: itt(r, "e2e_success") or 0.0)
            row += [
                f"{sc['ref_only_same_calls']} / {sc['ref_only']}",
                f"{sc['discordant_same_calls']} / {sc['discordant']}",
            ]
            js["same_calls"].setdefault(f"{a}-E0", {})[tag] = sc
        s_rows.append(row)
    lines += md_table(
        [
            "pair",
            "legacy: E0-only with same calls",
            "legacy: all discordant with same calls",
            "sym: E0-only with same calls",
            "sym: all discordant with same calls",
        ],
        s_rows,
    )

    lines += [
        "## 5. Executor variance runs (rep2 on 60 cases)",
        "",
        "Same routing decisions (cache), executor resampled. `flips` = cases (of 60) whose e2e verdict differs between rep 1 "
        "(main run) and rep 2.",
        "",
    ]
    v_rows = []
    for (label, _name), main in zip(VARIANCE, ("E0", "E9"), strict=True):
        row = [label]
        for src, tag in ((legacy, "legacy"), (sym, "sym")):
            r2 = {r["case_id"]: itt(r, "e2e_success") for r in src[label]}
            r1 = {r["case_id"]: itt(r, "e2e_success") for r in src[main] if r["case_id"] in r2}
            flips = sum(1 for c in r2 if r1[c] != r2[c])
            row += [f"{100 * sum(r2.values()) / len(r2):.1f}", f"{flips}/{len(r2)}"]
            js["variance"].setdefault(label, {})[tag] = {
                "e2e_rep2": sum(r2.values()) / len(r2),
                "flips": flips,
                "n": len(r2),
            }
        v_rows.append(row)
    lines += md_table(
        ["run", "legacy rep2 e2e %", "legacy flips", "sym rep2 e2e %", "sym flips"], v_rows
    )

    lines += [
        "## 6. Provenance",
        "",
        f"Symmetric scorer hash: {', '.join(sorted(sym_hash))}. Legacy scorer hash: e0eef1fb0073 (unchanged, asserted by "
        "`tests/test_phase1_hashes.py`). Re-score command: `uv run study rescore results/<run>.jsonl --scorer sym`.",
        "",
    ]
    lines += md_table(["run", "rows", "raw sha256", "legacy scorer", "sym scorer"], sources)
    lines += [
        "Caveats: post hoc, same test split as the confirmatory analysis, one executor sample per case (the rep2 runs above "
        "bound the executor noise). These numbers feed the H1-L effect-size and MDE assumptions of prereg-v2. They are "
        "not a phase-1 result.",
        "",
    ]
    write(OUT / "exploratory_e2e_sym.md", "\n".join(lines))
    write_json(OUT / "exploratory_e2e_sym.json", js)
    print(
        f"H3 legacy {fmt(h3['legacy (pre-registered, confirmatory in phase 1)']['delta'])} | sym {fmt(h3['symmetric (EXPLORATORY)']['delta'])}"
    )


if __name__ == "__main__":
    main()
