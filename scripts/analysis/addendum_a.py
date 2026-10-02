# ruff: noqa: E501  (report prose and table rows)
"""Part A (cloud addendum, prereg-v2a) analysis on test-v2, offline and idempotent.

Usage: uv run python scripts/analysis/addendum_a.py [--no-figures]

Reads only: results/rescored/{v2a-*,lat-a-*} (Part A), the re-used phase-1 rescored rows
(v2-e6b-qwen-canonical-routing-r1, v2-e3-embedding-routing-r1, v2-e10-classifier-routing-r1,
v2-e6b-qwen-canonical-repeat50, lat-{qwen,embedding,classifier,jev,haiku}-b*),
results/phase2a/run-manifest.log, config/ and docs/results/final/estimation.json (the phase-1
analysis of record, for the context arms of the figures and of the enterprise matrix).
Writes docs/results/addendum-a/{primary,estimation,enterprise_matrix}.{md,json} and
estudos/figuras/final-a-*.png.

prereg-v2a §8 names the script `addendum_all.py` and the folder `docs/results/addendum/`; the
T2.6 task named them `addendum_a.py` / `docs/results/addendum-a/` (naming only, logged as a
deviation). The statistics are the phase-1 machinery unchanged (routing_study.eval.stats via
final_common / final_primary / final_estimation): ITT, per-case means, paired cluster bootstrap
over case ids, 10 000 resamples, seed 20260930, sign-flip p, Holm within family A.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from final_common import (  # noqa: E402
    RESCORED,
    ROOT,
    Context,
    Run,
    by_case,
    ci_json,
    fms,
    fmt,
    itt_keys,
    md_table,
    prefix_sizes,
    resample_idx,
    rows_of,
    write,
    write_json,
)
from final_enterprise import SLO_MS, candidates, matrix  # noqa: E402
from final_estimation import _flip, _lat_rows, calibration_table, strategy_table  # noqa: E402
from final_primary import _contrast_rows, _pairwise_error_free  # noqa: E402

from routing_study.eval.manifest import load_manifest  # noqa: E402
from routing_study.eval.report import itt  # noqa: E402
from routing_study.eval.stats import (  # noqa: E402
    Contrast,
    bootstrap_mean,
    bootstrap_stat,
    evaluate_contrasts,
    paired_delta,
)

OUT = ROOT / "docs" / "results" / "addendum-a"
LOG_A = ROOT / "results" / "phase2a" / "run-manifest.log"
MANIFEST_A = ROOT / "config" / "addendum_manifest.yaml"
MANIFEST_1 = ROOT / "config" / "study_manifest.yaml"
PHASE1_EST = ROOT / "docs" / "results" / "final" / "estimation.json"

# ------------------------------------------------------------------ frozen values (prereg-v2a §1, §6)

CATALOG = "128584617807"
PROMPT = "c61ad0a7b7f8"
SCORER = "e0eef1fb0073"
DATASET_SHA = "6637c4795b2340b953ac5867498c1aeba7953fea25d76b8614de265cf2902a66"
MANIFEST_SHA = "177e374a8ee0f07303fc0244110c0ac5fa95f6b276d9006d30f2cdd54ac1149e"
CONFIG_A = {  # §1 per-run config hashes
    "v2a-e3c-cohere-routing-r1": "56f1708d24de",
    "v2a-e3t-titan-routing-r1": "73f81417a487",
    "v2a-e10c-cohere-routing-r1": "fc05bbd1c5aa",
    "v2a-e10t-titan-routing-r1": "70374caa4b59",
    "v2a-e6m-ministral-canonical-routing-r1": "0d8fbee553f3",
    "v2a-e6m-ministral-canonical-repeat50": "0d8fbee553f3",
    "v2a-e6n-nemotron-canonical-routing-r1": "efb00ce5b9f8",
    "v2a-e6n-nemotron-canonical-repeat50": "efb00ce5b9f8",
}
CONFIG_LAT_A = {
    "e3c": "dc14a444fd4b",
    "e3t": "310f335fdb80",
    "e10c": "ab5f1d2d0d13",
    "e10t": "6377e34f786e",
    "e6m": "67e47f9c08e8",
    "e6n": "435d2cee8b41",
    "jev": "5cf75faa33f3",
    "haiku": "5535a7588de0",
}
REUSED = {  # §1 re-used phase-1 rows: (config_hash, sha256 prefix of the rescored file)
    "v2-e6b-qwen-canonical-routing-r1": ("903a4a1e56d3", "6a99aab7fc6b116d"),
    "v2-e3-embedding-routing-r1": ("1899b6f414a5", "4c13be42cda91614"),
    "v2-e10-classifier-routing-r1": ("616af886b783", "b14c2893e454ce80"),
}

ARMS = [
    Run(
        "E3c",
        "v2a-e3c-cohere-routing-r1",
        "E3c Cohere Embed v4 router",
        "managed-semantic",
        "confirmatory (A3)",
        lat="a-e3c",
        local=False,
    ),
    Run(
        "E3t",
        "v2a-e3t-titan-routing-r1",
        "E3t Titan v2 router",
        "managed-semantic",
        "confirmatory (A4)",
        lat="a-e3t",
        local=False,
    ),
    Run(
        "E10c",
        "v2a-e10c-cohere-routing-r1",
        "E10c probe on Cohere vectors",
        "managed-semantic",
        "estimation",
        lat="a-e10c",
        local=False,
    ),
    Run(
        "E10t",
        "v2a-e10t-titan-routing-r1",
        "E10t probe on Titan vectors",
        "managed-semantic",
        "estimation",
        lat="a-e10t",
        local=False,
    ),
    Run(
        "E6m",
        "v2a-e6m-ministral-canonical-routing-r1",
        "E6m Ministral 3 8B",
        "api-llm",
        "confirmatory (A1)",
        lat="a-e6m",
        local=False,
    ),
    Run(
        "E6n",
        "v2a-e6n-nemotron-canonical-routing-r1",
        "E6n Nemotron Nano 9B v2",
        "api-llm",
        "confirmatory (A2)",
        lat="a-e6n",
        local=False,
    ),
]
REFS = [
    Run(
        "E6b",
        "v2-e6b-qwen-canonical-routing-r1",
        "E6b Qwen3-8B local (phase 1)",
        "local-semantic",
        "reference (phase 1, re-used)",
        lat="qwen",
    ),
    Run(
        "E3",
        "v2-e3-embedding-routing-r1",
        "E3 qwen3-embedding 8B local (phase 1)",
        "local-semantic",
        "reference (phase 1, re-used)",
        lat="embedding",
    ),
    Run(
        "E10",
        "v2-e10-classifier-routing-r1",
        "E10 local probe (phase 1)",
        "local-semantic",
        "reference (phase 1, re-used)",
        lat="classifier",
    ),
]
PEER = {"E6m": "E6b", "E6n": "E6b", "E3c": "E3", "E3t": "E3", "E10c": "E10", "E10t": "E10"}
A_FAMILY = [
    ("A1", Contrast("E6m", "E6b", "A", "non_inferiority", 0.03)),
    ("A2", Contrast("E6n", "E6b", "A", "non_inferiority", 0.03)),
    ("A3", Contrast("E3c", "E3", "A", "two_sided")),
    ("A4", Contrast("E3t", "E3", "A", "two_sided")),
]
EST_DELTAS = [("E10c", "E10"), ("E10t", "E10"), ("E10c", "E3c"), ("E10t", "E3t")]
REPEATS_A = {
    "E6m Ministral 3 8B (50 cases x 2)": ("v2a-e6m-ministral-canonical-repeat50", "E6m"),
    "E6n Nemotron Nano 9B v2 (50 cases x 2)": ("v2a-e6n-nemotron-canonical-repeat50", "E6n"),
    "E6b Qwen3-8B local, phase 1 (context, 50 cases x 2)": (
        "v2-e6b-qwen-canonical-repeat50",
        "E6b",
    ),
}
LAT_A = ["e3c", "e3t", "e10c", "e10t", "e6m", "e6n", "jev", "haiku"]
LAT_LABEL = {
    "e3c": "E3c Cohere v4",
    "e3t": "E3t Titan v2",
    "e10c": "E10c probe/Cohere",
    "e10t": "E10t probe/Titan",
    "e6m": "E6m Ministral 3 8B",
    "e6n": "E6n Nemotron 9B",
    "jev": "E4 Jev (anchor)",
    "haiku": "E6 Haiku 4.5 (anchor)",
    "qwen": "E6b Qwen3-8B local",
    "embedding": "E3 qwen3-emb 8B local",
    "classifier": "E10 probe local",
}
LAT_1_LOCAL = ["qwen", "embedding", "classifier"]
LAT_1_ANCHORS = ["jev", "haiku"]
LAT_PEER = {
    "e3c": "embedding",
    "e3t": "embedding",
    "e10c": "classifier",
    "e10t": "classifier",
    "e6m": "qwen",
    "e6n": "qwen",
}
NI_MARGIN = 0.03
CAVEAT = (
    "**Window caveat (prereg-v2a §3, mandatory):** the local rows are the phase-1 lat-* blocks, measured in a "
    "different time window from the Part-A blocks; same Mac (M5 Pro 48 GB) for the local side, Bedrock `sa-east-1` "
    "(Jev: OpenRouter) called from that Mac for the managed side. Drift is estimated from the managed anchors (Jev, "
    "Haiku 4.5) re-run in both windows; it is reported, never subtracted."
)


# ------------------------------------------------------------------ provenance


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def log_status() -> dict[str, str]:
    """run name -> last status word in the Part-A manifest log."""
    out: dict[str, str] = {}
    pat = re.compile(r"^\S+ (COMPLETE|FLAGGED|ABORT\w*|REFUSED|SKIP\w*|RUN|RESCORED) ([^:\s]+)")
    for line in LOG_A.read_text(encoding="utf-8").splitlines():
        m = pat.match(line)
        if m:
            out[m.group(2)] = m.group(1)
    return out


def _check_rows(name: str, rows: list[dict[str, Any]], config_hash: str, prompt_hash: str) -> None:
    for r in rows:
        got = (
            r.get("catalog_hash"),
            r.get("config_hash"),
            r.get("prompt_hash"),
            r.get("scorer_hash"),
            r.get("dataset_sha256"),
        )
        want = (CATALOG, config_hash, prompt_hash, SCORER, DATASET_SHA)
        if got != want:
            raise SystemExit(f"hash mismatch in {name} case {r.get('case_id')}: {got} != {want}")
    keys = {(r["case_id"], r["rep"]) for r in rows}
    if len(keys) != len(rows):
        raise SystemExit(f"duplicate (case, rep) keys in {name}")


def check_provenance() -> list[list[Any]]:
    """Assert prereg-v2a §1/§6 on every row of every run used here; return the audit table."""
    if _sha256(MANIFEST_A) != MANIFEST_SHA:
        raise SystemExit("config/addendum_manifest.yaml sha256 differs from prereg-v2a §6")
    if _sha256(ROOT / "data" / "dataset_test_v2.jsonl") != DATASET_SHA:
        raise SystemExit("data/dataset_test_v2.jsonl sha256 differs from prereg-v2a §1")
    st = log_status()
    ma = {r.name: r for r in load_manifest(MANIFEST_A).runs}
    m1 = {r.name: r for r in load_manifest(MANIFEST_1).runs}
    if len(ma) != 40:
        raise SystemExit(f"addendum manifest has {len(ma)} runs, expected 40")
    audit = []
    for name, r in ma.items():
        want = CONFIG_A.get(name) or CONFIG_LAT_A[name.split("-")[2]]
        if r.config_hash != want or r.prompt_hash != PROMPT:
            raise SystemExit(f"{name}: manifest hashes differ from prereg-v2a §1")
        if st.get(name) != "COMPLETE":
            raise SystemExit(f"{name}: not COMPLETE in {LOG_A} ({st.get(name)})")
        rows = rows_of(name)
        if rows is None:
            raise SystemExit(f"{name}: rescored file missing")
        _check_rows(name, rows, r.config_hash, PROMPT)
        if not name.startswith("lat-"):
            audit.append(
                [
                    name,
                    "Part A",
                    len(rows),
                    r.config_hash,
                    "COMPLETE",
                    sum(1 for x in rows if x.get("error")),
                ]
            )
    lat_a = sum(1 for n in ma if n.startswith("lat-a-"))
    audit.append(
        [
            f"lat-a-* ({lat_a} blocks)",
            "Part A",
            25 * lat_a,
            "per §1",
            "COMPLETE (all)",
            "see estimation.md",
        ]
    )
    phase1 = [*REUSED, "v2-e6b-qwen-canonical-repeat50"] + [
        f"lat-{s}-b{b}" for s in LAT_1_LOCAL + LAT_1_ANCHORS for b in (1, 2, 3, 4)
    ]
    for name in phase1:
        r = m1[name]
        rows = rows_of(name)
        if rows is None:
            raise SystemExit(f"{name}: phase-1 rescored file missing or not COMPLETE")
        _check_rows(name, rows, r.config_hash, PROMPT)
        if name in REUSED:
            cfg, sha = REUSED[name]
            if r.config_hash != cfg or not _sha256(RESCORED / f"{name}.jsonl").startswith(sha):
                raise SystemExit(f"{name}: re-used file differs from prereg-v2a §1")
            audit.append(
                [
                    name,
                    "phase 1 (re-used)",
                    len(rows),
                    r.config_hash,
                    f"sha256 {sha}… ok",
                    sum(1 for x in rows if x.get("error")),
                ]
            )
    audit.append(
        [
            "lat-{qwen,embedding,classifier,jev,haiku}-b1..4",
            "phase 1 (re-used)",
            25 * 20,
            "per study_manifest",
            "COMPLETE (all)",
            "see estimation.md",
        ]
    )
    return audit


def load_ctx() -> Context:
    ctx = Context()
    for run in ARMS + REFS:
        rows = rows_of(run.name)
        assert rows is not None
        ctx.routing[run.key], ctx.runs[run.key] = rows, run
    return ctx


# ------------------------------------------------------------------ family A (confirmatory)


def _direction(res: dict[str, Any], verdict: str) -> str:
    c = res["contrast"]
    if c.kind != "two_sided" or "delta_ci" not in res:
        return verdict
    lo, hi = res["delta_ci"][1], res["delta_ci"][2]
    if hi < 0:
        return verdict + f" ({c.run.split('#')[0]} lower)"
    if lo > 0:
        return verdict + f" ({c.run.split('#')[0]} higher)"
    return verdict


def family_a(ctx: Context, audit: list[list[Any]]) -> tuple[list[str], dict[str, Any]]:
    names = [n for n, _ in A_FAMILY]
    contrasts = [c for _, c in A_FAMILY]
    scores = {k: itt_keys(rs, "joint_correct") for k, rs in ctx.routing.items()}
    header = [
        "id",
        "run",
        "reference",
        "kind",
        "n cases",
        "Δ joint pp [95% CI] (paired cluster bootstrap)",
        "McNemar case-level run-only/ref-only",
        "sign-flip p",
        "Holm p (A1-A4)",
        "reject @0.05",
        "verdict (CI rule)",
    ]
    out: dict[str, Any] = {
        "status": "CONFIRMATORY (prereg-v2a family A, Holm across A1-A4, alpha 0.05)"
    }
    lines = [
        "# Part A primary analysis (CONFIRMATORY): prereg-v2a family A on test-v2",
        "",
        "Generated by `scripts/analysis/addendum_a.py` (offline, from `results/rescored/`; scorer e0eef1fb0073). Joint = joint top-1 "
        "routing accuracy, ITT (an infra or parse failure is wrong), 1 rep per arm, paired by case over the 349 test-v2 cases. Paired "
        "cluster bootstrap over case ids, 10 000 resamples, seed 20260930; p = case-level sign-flip (non-inferiority: shift +0.03, "
        "one-sided); Holm step-down across A1-A4 (α 0.05). The references are the frozen phase-1 local rows, re-used read-only "
        "(no local model was run in phase 2).",
        "",
        "- **A1 (NI, margin 3 pp):** Joint(E6m Ministral 3 8B, Bedrock) − Joint(E6b Qwen3-8B local) > −3 pp.",
        "- **A2 (NI, margin 3 pp):** Joint(E6n Nemotron Nano 9B v2, Bedrock) − Joint(E6b) > −3 pp.",
        "- **A3 (two-sided):** Joint(E3c Cohere Embed v4 router) − Joint(E3 local qwen3-embedding 8B).",
        "- **A4 (two-sided):** Joint(E3t Titan Text Embeddings v2 router) − Joint(E3).",
        "",
    ]
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
        for row, j, res in zip(table, js, results, strict=True):
            row[1], row[2] = str(row[1]).split("#")[0], str(row[2]).split("#")[0]
            j["run"], j["reference"] = row[1], row[2]
            row[-1] = j["verdict"] = _direction(res, row[-1])
        lines += [f"## Family A: {label}", ""] + md_table(header, table)
        if err_free:
            lines += [
                "Cases error-free in both runs: "
                + ", ".join(f"{n} {s}" for n, s in zip(names, sizes, strict=True))
                + " (of 349).",
                "",
            ]
        out["error_free" if err_free else "itt"] = js
    # per-arm headline
    hrow = []
    for k in ("E6m", "E6n", "E6b", "E3c", "E3t", "E3"):
        rs = ctx.routing[k]
        ci = bootstrap_mean(by_case(rs, lambda r: itt(r, "joint_correct")))
        hrow.append(
            [
                ctx.runs[k].label,
                ctx.runs[k].name,
                ctx.runs[k].status,
                len(rs),
                sum(1 for r in rs if r.get("error")),
                fmt(ci),
            ]
        )
        out.setdefault("headline", {})[k] = {"run": ctx.runs[k].name, "joint": ci_json(ci)}
    lines += ["## Headline joint per arm (ITT, 95% cluster-bootstrap CI)", ""]
    lines += md_table(["arm", "run", "status", "rows", "error rows", "joint % [95% CI]"], hrow)
    lines += ["## Decision summary", ""]
    srow = []
    for j in out["itt"]:
        d = j["delta"]
        if j["kind"] == "non_inferiority":
            ci_ok = d["lo"] > -NI_MARGIN
            reading = (
                "non-inferiority SHOWN by the CI rule"
                if ci_ok
                else "non-inferiority NOT shown by the CI rule"
            ) + (
                "; Holm sign-flip rejects Δ ≤ −3 pp"
                if j["reject_holm_0.05"]
                else "; Holm sign-flip does not reject Δ ≤ −3 pp"
            )
        else:
            ci_ok = d["lo"] > 0 or d["hi"] < 0
            reading = (
                ("difference: " + j["verdict"]) if ci_ok else "no directional claim (CI includes 0)"
            )
            reading += (
                "; Holm rejects Δ = 0" if j["reject_holm_0.05"] else "; Holm does not reject Δ = 0"
            )
        srow.append(
            [
                j["id"],
                f"{j['run']} − {j['reference']}",
                fmt([d["point"], d["lo"], d["hi"]]),
                f"{j['p_holm']:.4g}",
                reading,
            ]
        )
    lines += md_table(["id", "contrast", "Δ pp [95% CI]", "Holm p", "reading"], srow)
    lines += [
        "## Reading rules (pre-registered)",
        "",
        "- A1/A2: non-inferior iff the lower bound of the two-sided 95% paired CI of Δ (= one-sided 97.5%) is above −3 pp "
        "(prereg-v1 rule, inherited by prereg-v2a §0). The Holm-adjusted sign-flip p tests H0: Δ ≤ −3 pp. Both are shown; "
        "when they disagree the CI rule is the pre-registered decision and the Holm column is the multiplicity-controlled test.",
        "- A3/A4: two-sided; a directional claim only if the CI excludes 0. Holm-adjusted sign-flip p of H0: Δ = 0.",
        "- ITT: a parse failure is an error row and counts as wrong (E6m has 2 such rows; estimation.md §E). The error-free "
        "sensitivity restricts each contrast to the cases error-free in both of its runs.",
        "- Dev expectation (not a test; docs/tuning-effort-l.md §A): E6m 79.5, E6n 78.1 vs E6b 82.2 (dev CV); E3c 59.6, "
        "E3t 60.3 vs E3 77.5 (nested CV).",
        "",
        "## Provenance (asserted on every row: prereg-v2a §1, §6, §8)",
        "",
        "Every row of every run below carries catalog_hash 128584617807, prompt_hash c61ad0a7b7f8, scorer_hash e0eef1fb0073, "
        "dataset sha256 6637c479…, and the config_hash frozen in prereg-v2a §1 (Part A) or in `config/study_manifest.yaml` "
        "(phase 1); the addendum manifest sha256 is 177e374a…; every Part-A run is COMPLETE in results/phase2a/run-manifest.log; "
        "the re-used phase-1 files match their §1 sha256 prefixes. The script stops on any mismatch.",
        "",
    ]
    lines += md_table(
        ["run", "source", "rows", "config_hash", "status / check", "error rows (ITT)"], audit
    )
    out["provenance"] = audit
    return lines, out


# ------------------------------------------------------------------ latency


def lat_summary(prefix: str) -> dict[str, Any]:
    rows = _lat_rows(prefix)
    if len(rows) != 100:
        raise SystemExit(f"lat-{prefix}-b*: {len(rows)} rows, expected 100")
    warm = {
        r["case_id"]: float(r["latency_ms"]["routing"])
        for b, i, r in rows
        if i > 0 and not r.get("error")
    }
    cold = [float(r["latency_ms"]["routing"]) for b, i, r in rows if i == 0]
    pct = {
        q: bootstrap_stat(
            {c: [v] for c, v in warm.items()}, lambda a, q=q: float(np.percentile(a, q))
        )
        for q in (50, 95, 99)
    }
    return {
        "n_warm": len(warm),
        "n_cold": len(cold),
        "errors": sum(1 for _, _, r in rows if r.get("error")),
        "warm": {str(q): ci_json(v) for q, v in pct.items()},
        "cold_ms": cold,
        "warm_by_case": dict(sorted(warm.items())),
        "bench_joint": float(np.mean([itt(r, "joint_correct") or 0.0 for _, _, r in rows])),
    }


def pct_delta(
    a: dict[str, float], b: dict[str, float], q: float
) -> tuple[float, float, float, int]:
    """Paired (same case ids) cluster-bootstrap CI of percentile_q(a) − percentile_q(b)."""
    keys = sorted(set(a) & set(b), key=str)
    x = np.array([a[k] for k in keys])
    y = np.array([b[k] for k in keys])
    idx = resample_idx(len(keys))
    d = np.percentile(x[idx], q, axis=1) - np.percentile(y[idx], q, axis=1)
    lo, hi = np.percentile(d, [2.5, 97.5])
    return float(np.percentile(x, q) - np.percentile(y, q)), float(lo), float(hi), len(keys)


def _lat_row(name: str, window: str, where: str, s: dict[str, Any]) -> list[Any]:
    cold = s["cold_ms"]
    return [
        name,
        window,
        where,
        s["n_warm"],
        fms([s["warm"]["50"][x] for x in ("point", "lo", "hi")]),
        fms([s["warm"]["95"][x] for x in ("point", "lo", "hi")]),
        fms([s["warm"]["99"][x] for x in ("point", "lo", "hi")]),
        f"{median(cold):.0f} / {max(cold):.0f}",
        s["errors"],
        f"{100 * s['bench_joint']:.1f}",
    ]


def latency(lat_a: dict[str, Any], lat_1: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    hdr = [
        "strategy",
        "window",
        "where",
        "warm n",
        "p50 ms [95% CI]",
        "p95 ms [95% CI]",
        "p99 ms [95% CI]",
        "cold first case ms median / max",
        "error rows",
        "bench joint % (100 cases)",
    ]
    same = [
        _lat_row(LAT_LABEL[s], "Part A", "Bedrock" if s != "jev" else "OpenRouter", lat_a[s])
        for s in LAT_A
    ]
    other = [_lat_row(LAT_LABEL[s], "phase 1", "local (Mac)", lat_1[s]) for s in LAT_1_LOCAL]
    other += [
        _lat_row(LAT_LABEL[s], "phase 1", "Bedrock" if s == "haiku" else "OpenRouter", lat_1[s])
        for s in LAT_1_ANCHORS
    ]
    js: dict[str, Any] = {"drift": {}, "vs_local": {}}
    drift = []
    for s in LAT_1_ANCHORS:
        row = [LAT_LABEL[s]]
        for q in (50, 95):
            d = pct_delta(lat_a[s]["warm_by_case"], lat_1[s]["warm_by_case"], q)
            js["drift"][f"{s}|p{q}"] = {"point": d[0], "lo": d[1], "hi": d[2], "n": d[3]}
            row.append(fmt(d[:3], 1.0, 0))
        row.append(d[3])
        drift.append(row)
    vs = []
    for s, peer in LAT_PEER.items():
        row = [LAT_LABEL[s], LAT_LABEL[peer]]
        for q in (50, 95):
            d = pct_delta(lat_a[s]["warm_by_case"], lat_1[peer]["warm_by_case"], q)
            js["vs_local"][f"{s}|p{q}"] = {"point": d[0], "lo": d[1], "hi": d[2], "n": d[3]}
            row.append(fmt(d[:3], 1.0, 0))
        row.append(d[3])
        vs.append(row)
    lines = [
        "## G. Latency (ESTIMATION; dedicated benchmark only)",
        "",
        "The phase-1 100 stratified test-v2 cases (`config/manifest/latency_test_v2_b{1..4}.ids`) in 4 blocks of 25, block-level "
        "interleaving, concurrency 1, response caches off, fresh vector cache (`.cache/latency-a`). Routing latency (skill + tool "
        "stage) per case. The first case of each block is **cold** and reported apart (median / max of the 4); the other 96 are "
        "**warm**; error rows (parse failures turned into errors by the rescore) are left out of the warm set and counted in the "
        "error column (phase-1 rule). 95% CIs: cluster bootstrap over cases (10k, seed 20260930); p99 of 96 values is near the sample maximum (a tail "
        "indicator). Accuracy numbers come from the 349-case runs, not from this benchmark (its 100-case joint is shown for reference).",
        "",
        "### G1. Same window: the six new managed arms and the managed anchors (Part A, interleaved by block)",
        "",
    ]
    lines += md_table(hdr, same)
    lines += [
        "### G2. Other window: phase-1 local blocks (and the phase-1 anchor blocks used for drift)",
        "",
        CAVEAT,
        "",
    ]
    lines += md_table(hdr, other)
    lines += [
        "### G3. Drift of the managed anchors (Part A − phase 1, same 96 warm case ids, paired bootstrap)",
        "",
        "Reported, never subtracted. A positive Δ = the provider was slower in the Part-A window.",
        "",
    ]
    lines += md_table(
        ["anchor", "Δ p50 ms [95% CI]", "Δ p95 ms [95% CI]", "paired warm cases"], drift
    )
    lines += [
        "### G4. New managed arm − its local peer (cross-window; same 96 warm case ids, paired bootstrap)",
        "",
        CAVEAT,
        "",
    ]
    lines += md_table(
        [
            "managed arm (Part A)",
            "local peer (phase 1)",
            "Δ p50 ms [95% CI]",
            "Δ p95 ms [95% CI]",
            "paired warm cases",
        ],
        vs,
    )
    return lines, js


# ------------------------------------------------------------------ estimation


def _retitle(lines: list[str], old: str, new: str) -> list[str]:
    return [new + ln[len(old) :] if ln.startswith(old) else ln for ln in lines]


COST_REGIMES = [
    "- **observed**: `cost_usd.routing` as recorded per row (the regime of the phase-1 H1 co-primary): every consulted stage's "
    "recorded cost. For the embedding routers each stage records the query embedding; the tool stage of E3c/E3t reuses the "
    "cached query vector, so the billed cost (§C) is about half of it;",
    "- **list uncached**: recorded tokens × list price (`config/prices.yaml`; Ministral 3 8B and Nemotron Nano 2 at the higher of "
    "the two listed sa-east-1 rates, embeddings at the us-east-1 list price), no prompt-cache discount; local = 0;",
    "- **modelled cache**: the phase-1 Poisson/TTL model (5-minute TTL refreshed on hit, per prompt prefix). None of the Part-A "
    "models has a cache price or an observed cache read, so the modelled regime equals list uncached for every Part-A arm "
    "(a model statement, not a measurement).",
]


def strategies(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    rows = [r for rs in ctx.routing.values() for r in rs]
    lines, js = strategy_table(ctx, prefix_sizes(rows))
    lines = _retitle(lines, "## A. Per strategy", "## A. Per arm")
    i = next(n for n, ln in enumerate(lines) if ln.startswith("- **observed**"))
    j = next(n for n in range(i, len(lines)) if lines[n] == "")
    lines = lines[:i] + COST_REGIMES + lines[j:]
    # billed (what the ledger was charged)
    brow = []
    for k, rs in ctx.routing.items():
        b = bootstrap_mean(by_case(rs, lambda r: (r.get("cost_usd") or {}).get("routing_billed")))
        js[k]["cost_billed_per_case"] = ci_json(b)
        o = js[k]["cost_observed_per_case"]
        brow.append(
            [
                ctx.runs[k].label,
                fmt(b, 1000, 4),
                fmt([o[x] for x in ("point", "lo", "hi")], 1000, 4),
            ]
        )
    lines += [
        "### C. Billed routing cost per 1 000 cases (US$; `cost_usd.routing_billed`)",
        "",
        "What the provider was charged for the routing calls of the run (response-cache hits and query-vector reuse bill 0). "
        "E10c/E10t show 0: the budget guard prices the probe's Bedrock query embeddings as free (prereg-v2a §6 note); their real "
        "cost is the list-uncached column of §A.",
        "",
    ]
    lines += md_table(["arm", "billed US$/1k [95% CI]", "observed US$/1k [95% CI]"], brow)
    return lines, js


def est_deltas(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    md = []
    for a, b in EST_DELTAS:
        out = {}
        row = [f"{a} − {b}"]
        for score, lab in (("joint_correct", "joint"), ("skill_correct", "skill")):
            d = paired_delta(itt_keys(ctx.routing[a], score), itt_keys(ctx.routing[b], score))
            out[lab] = ci_json(d)
            row.append(fmt(d))
        js[f"{a}-{b}"] = out
        md.append(row)
    lines = [
        "## B. Probes vs their local peer and vs their own embedding router (ESTIMATION: paired Δ, no test)",
        "",
        "Paired cluster bootstrap over the 349 shared cases (10k, seed 20260930), ITT.",
        "",
    ]
    return lines + md_table(["contrast", "Δ joint pp [95% CI]", "Δ skill pp [95% CI]"], md), js


def errors_parse(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    md = []
    for k, rs in ctx.routing.items():
        calls = pf = retried = 0
        for r in rs:
            for lv in ("skill", "tool"):
                for st in (r.get(lv) or {}).get("steps") or []:
                    u = st.get("usage") or {}
                    calls += 1
                    pf += bool(u.get("parse_fail"))
                    retried += int(u.get("attempts") or 1) > 1
        err = Counter(str(r["error"]) for r in rs if r.get("error"))
        n_err = sum(err.values())
        err_ci = bootstrap_mean({r["case_id"]: [float(bool(r.get("error")))] for r in rs})
        js[k] = {
            "rows": len(rs),
            "error_rows": n_err,
            "error_kinds": dict(sorted(err.items())),
            "error_rate": ci_json(err_ci),
            "stage_calls": calls,
            "parse_fail_calls": pf,
            "parse_fail_rate_calls": pf / calls if calls else None,
            "calls_with_retry": retried,
        }
        md.append(
            [
                ctx.runs[k].label,
                len(rs),
                f"{n_err} ({fmt(err_ci)})",
                ", ".join(f"{e} ×{n}" for e, n in sorted(err.items())) or "-",
                calls,
                f"{pf} ({100 * pf / calls:.2f}%)" if calls else "-",
                retried,
            ]
        )
    lines = [
        "## E. Error and parse-failure rates (ESTIMATION; ITT)",
        "",
        "Error row = the rescored row carries an error (counted wrong under ITT). Parse failure = a stage call whose structured "
        "output failed validation (`usage.parse_fail`); the rescore turns it into an error row although the manifest log counted "
        "0 infra errors (the same mechanism as the 2 phase-1 E4 Jev rows). Stage calls = skill + tool stage calls (2 per row).",
        "",
    ]
    lines += md_table(
        [
            "arm",
            "rows",
            "error rows n (% [95% CI])",
            "kinds",
            "stage calls",
            "parse-fail calls n (% of calls)",
            "calls with a provider retry",
        ],
        md,
    )
    return lines, js


def flips(ctx: Context) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    md = []
    for label, (name, main_key) in REPEATS_A.items():
        rs = rows_of(name)
        assert rs is not None
        r1 = [r for r in rs if r["rep"] == 1]
        r2 = [r for r in rs if r["rep"] == 2]
        main = {r["case_id"]: r for r in ctx.routing[main_key]}
        mism = sum(
            1
            for r in r1
            if ((r.get("skill") or {}).get("choice"), (r.get("tool") or {}).get("choice"))
            != (
                (main[r["case_id"]].get("skill") or {}).get("choice"),
                (main[r["case_id"]].get("tool") or {}).get("choice"),
            )
        )
        f = _flip(r1, r2)
        f["rep1_vs_r1_mismatches"] = mism
        js[label] = f
        md.append(
            [
                label,
                name,
                f["n"],
                f"{f['decision_flips']} ({fmt([f['decision_flip'][x] for x in ('point', 'lo', 'hi')])})",
                f"{f['joint_flips']} ({fmt([f['joint_flip'][x] for x in ('point', 'lo', 'hi')])})",
                mism,
            ]
        )
    lines = [
        "## F. Flip rate rep 1 vs rep 2 on the 50 stratified cases (ESTIMATION)",
        "",
        "Rep 1 = cache hit of the r1 run (checked: the last column counts rep-1 decisions that differ from the r1 row; 0 = identical), "
        "rep 2 = a fresh call at temperature 0. decision flip = (skill, tool) choice differs; joint flip = correctness differs. % [95% CI] over cases.",
        "",
    ]
    lines += md_table(
        [
            "arm",
            "run",
            "cases",
            "decision flips n (% [CI])",
            "joint flips n (% [CI])",
            "rep-1 ≠ r1 decisions",
        ],
        md,
    )
    return lines, js


def cohere_region() -> tuple[list[str], dict[str, Any]]:
    names = ["v2a-e3c-cohere-routing-r1", "v2a-e10c-cohere-routing-r1"] + [
        f"lat-a-{s}-b{b}" for s in ("e3c", "e10c") for b in (1, 2, 3, 4)
    ]
    served: Counter[str] = Counter()
    keys: set[str] = set()
    for n in names:
        for r in rows_of(n) or []:
            for lv in ("skill", "tool"):
                for st in (r.get(lv) or {}).get("steps") or []:
                    u = st.get("usage") or {}
                    served[f"{u.get('provider')} / {u.get('served_model')}"] += 1
                    keys |= set(u)
    cfg = {}
    for c in ("e3_embedding_cohere", "e10_classifier_cohere"):
        y = yaml.safe_load(
            (ROOT / "config" / "experiments" / f"{c}.yaml").read_text(encoding="utf-8")
        )
        e = (y.get("strategies") or {}).get("embedding") or {}
        cfg[c] = {"model": e.get("model"), "region": e.get("region")}
    region_fields = sorted(k for k in keys if "region" in k.lower())
    js = {
        "served": dict(sorted(served.items())),
        "configured": cfg,
        "usage_region_fields": region_fields,
        "served_region": "not reported (no region field in any row)"
        if not region_fields
        else region_fields,
    }
    lines = [
        "## H. Served region for Cohere Embed v4 (ESTIMATION / descriptive)",
        "",
        "Configured: "
        + "; ".join(
            f"`{c}` → model `{v['model']}`, client region `{v['region']}`" for c, v in cfg.items()
        )
        + ".",
        "",
    ]
    lines += md_table(
        ["provider / served model (all Cohere stage calls: test + latency runs)", "calls"],
        [[k, v] for k, v in sorted(served.items())],
    )
    lines += [
        f"Region fields in the recorded usage: {', '.join(region_fields) if region_fields else 'none'}. **Served region: not observable.** "
        "`global.cohere.embed-v4:0` is a cross-region inference profile called from `sa-east-1`; Bedrock InvokeModel does not "
        "report the serving region, so the Cohere latency (§G) includes whatever cross-region routing Bedrock applied "
        "(prereg-v2a §9). Titan (`amazon.titan-embed-text-v2:0`) and the two 8B models are in-region model ids.",
        "",
    ]
    return lines, js


def phase1_context(ctx: Context, lat_1: dict[str, Any]) -> dict[str, Any]:
    """Phase-1 analysis of record; cross-checked against the rows recomputed here."""
    est = json.loads(PHASE1_EST.read_text(encoding="utf-8"))
    for k in ("E6b", "E3", "E10"):
        mine = bootstrap_mean(by_case(ctx.routing[k], lambda r: itt(r, "joint_correct")))
        if mine is None or abs(est["strategies"][k]["joint"]["point"] - mine[0]) > 1e-12:
            raise SystemExit(f"phase-1 estimation.json joint of {k} differs from the rescored rows")
    for s in LAT_1_LOCAL + LAT_1_ANCHORS:
        for q in ("50", "95"):
            if abs(est["latency"][s]["warm"][q]["point"] - lat_1[s]["warm"][q]["point"]) > 1e-9:
                raise SystemExit(
                    f"phase-1 estimation.json p{q} of {s} differs from the lat-{s}-b* rows"
                )
    return est


# ------------------------------------------------------------------ enterprise matrix


def enterprise(
    prim: dict[str, Any],
    est_js: dict[str, Any],
    lat_a: dict[str, Any],
    lat_1: dict[str, Any],
    p1: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    ni = {j["run"]: j for j in prim["itt"]}
    rule_rows, rule_js = [], {}
    for k, peer in PEER.items():
        s = k.lower()
        p95 = lat_a[s]["warm"]["95"]
        if k in ni:
            d = ni[k]["delta"]
            basis = f"{ni[k]['id']} (confirmatory)"
        else:
            d = est_js["deltas"][f"{k}-{peer}"]["joint"]
            basis = "estimation Δ vs E10 (no test)"
        acc_ok = d["lo"] > -NI_MARGIN
        peer_p95 = lat_1[LAT_PEER[s]]["warm"]["95"]
        cells = {}
        row = [
            k,
            peer,
            basis,
            fmt([d["point"], d["lo"], d["hi"]]),
            "yes" if acc_ok else "no",
            fms([p95[x] for x in ("point", "lo", "hi")]),
        ]
        for slo in SLO_MS:
            lat_ok = p95["hi"] < slo
            q = lat_ok and acc_ok
            cells[str(slo)] = q
            why = [w for w, bad in (("p95", not lat_ok), ("accuracy", not acc_ok)) if bad]
            row.append("**qualifies**" if q else "no (" + ", ".join(why) + ")")
        row.append(fms([peer_p95[x] for x in ("point", "lo", "hi")]) + " (phase 1)")
        rule_rows.append(row)
        rule_js[k] = {
            "peer": peer,
            "basis": basis,
            "delta": d,
            "accuracy_ok": acc_ok,
            "p95": p95,
            "qualifies": cells,
            "peer_p95_phase1": peer_p95,
        }
    peer_rows = []
    for peer, s in (("E6b", "qwen"), ("E3", "embedding"), ("E10", "classifier")):
        p95 = lat_1[s]["warm"]["95"]
        peer_rows.append(
            [peer, LAT_LABEL[s], fms([p95[x] for x in ("point", "lo", "hi")])]
            + ["fits" if p95["hi"] < slo else "no" for slo in SLO_MS]
        )
    # the phase-1 matrix logic with the managed options added
    cands = candidates(p1)
    for c in cands:
        c["window"] = "phase 1"
    for run in ARMS:
        s = est_js["strategies"][run.key]
        cands.append(
            {
                "key": run.key,
                "label": run.label + " (managed)",
                "status": run.status,
                "joint": s["joint"],
                "cost": {x: 1000 * v for x, v in s["cost_observed_per_case"].items()},
                "cost_list": {x: 1000 * v for x, v in s["cost_list_uncached_per_case"].items()},
                "p95": lat_a[run.lat.split("-")[1]]["warm"]["95"],
                "local": False,
                "window": "Part A",
            }
        )
    m_lines, m_cells = matrix(cands)
    m_lines = _retitle(m_lines, "## Minimum", "### Minimum")
    budget_lines = []
    for slo in SLO_MS:
        q = [k for k in PEER if rule_js[k]["qualifies"][str(slo)]]
        locs = [
            r[0]
            for r in peer_rows
            if lat_1[{"E6b": "qwen", "E3": "embedding", "E10": "classifier"}[r[0]]]["warm"]["95"][
                "hi"
            ]
            < slo
        ]
        budget_lines.append(
            f"- **p95 < {slo:g} ms:** managed options qualifying under the prereg-v2a rule: {', '.join(q) or 'none'}; "
            f"local peers whose p95 upper CI fits (phase-1 window): {', '.join(locs) or 'none'}."
        )
    lines = [
        "# Enterprise decision matrix with the managed options (Part A, test-v2, routing-only)",
        "",
        "ESTIMATION / descriptive (no test beyond family A). Generated by `scripts/analysis/addendum_a.py`.",
        "",
        "## 1. Pre-registered qualification rule (prereg-v2a §3)",
        "",
        "A managed option **qualifies** at a latency budget when its warm p95 **upper** 95% CI is under the budget **and** its joint "
        "is not inferior to its local peer: for the 8B models the A1/A2 rule (lower bound of the 95% paired CI of Δ > −3 pp); for "
        "the embedders the A3/A4 CI excludes a loss larger than 3 pp (same bound). E10c/E10t are outside family A: their accuracy "
        "condition uses the estimation Δ vs the local probe E10 (labelled). Budgets: the phase-1 matrix SLOs.",
        "",
        CAVEAT,
        "",
    ]
    lines += md_table(
        [
            "managed",
            "local peer",
            "accuracy basis",
            "Δ joint pp vs peer [95% CI]",
            "not inferior (lo > −3 pp)",
            "warm p95 ms [95% CI] (Part A)",
        ]
        + [f"p95 < {s:g} ms" for s in SLO_MS]
        + ["peer warm p95 ms [95% CI]"],
        rule_rows,
    )
    lines += [
        "Local peers at the same budgets (p95 upper CI under the budget; phase-1 window):",
        "",
    ]
    lines += md_table(
        ["local peer", "lat block", "warm p95 ms [95% CI]"] + [f"p95 < {s:g} ms" for s in SLO_MS],
        peer_rows,
    )
    lines += ["### What qualifies at each latency budget", ""] + budget_lines + [""]
    lines += [
        "## 2. Phase-1 matrix logic re-derived with the managed options added",
        "",
        "Same logic as `docs/results/final/enterprise_matrix.md` (`final_enterprise.matrix`): per latency SLO (warm p95), routing-cost "
        "ceiling (US$/1k, observed regime) and minimum joint (ITT), the qualifying configuration with the highest joint point estimate "
        "(ties: lower cost); point estimates qualify, `robust` = the CIs also satisfy the three constraints. The phase-1 candidates "
        "keep their phase-1 numbers (accuracy, cost, and phase-1-window latency); the six managed arms use their Part-A runs and "
        "Part-A-window latency (window column). Local cost counted as US$ 0 (hardware and energy excluded); Jev cost is its "
        "reported OpenRouter price.",
        "",
        CAVEAT,
        "",
        "### Candidates",
        "",
    ]
    lines += md_table(
        [
            "config",
            "where",
            "latency window",
            "joint % [95% CI]",
            "warm p95 ms [95% CI]",
            "US$/1k observed [95% CI]",
            "US$/1k list uncached",
        ],
        [
            [
                c["label"],
                "local" if c["local"] else "API",
                c["window"],
                f"{100 * c['joint']['point']:.1f} [{100 * c['joint']['lo']:.1f}, {100 * c['joint']['hi']:.1f}]",
                f"{c['p95']['point']:.1f} [{c['p95']['lo']:.1f}, {c['p95']['hi']:.1f}]",
                f"{c['cost']['point']:.4f} [{c['cost']['lo']:.4f}, {c['cost']['hi']:.4f}]",
                f"{c['cost_list']['point']:.4f}",
            ]
            for c in sorted(cands, key=lambda c: (-c["joint"]["point"], c["key"]))
        ],
    )
    lines += m_lines
    lines += [
        "Cells marked `none qualifies` are a result (no benchmarked configuration meets all three constraints), not missing data.",
        "",
    ]
    js = {"rule": rule_js, "local_peers": peer_rows, "candidates": cands, "cells": m_cells}
    return "\n".join(lines), js


# ------------------------------------------------------------------ figures


def figure_data(
    ctx: Context,
    est_js: dict[str, Any],
    lat_a: dict[str, Any],
    lat_1: dict[str, Any],
    p1: dict[str, Any],
) -> dict[str, Any]:
    pts = []
    for k, s in p1["strategies"].items():
        if not s.get("lat") or s["lat"] not in p1["latency"]:
            continue
        pts.append(
            {
                "key": k,
                "phase": "phase 1",
                "local": s["local"],
                "joint": s["joint"],
                "cost_1k": {x: 1000 * v for x, v in s["cost_observed_per_case"].items()},
                "p95": p1["latency"][s["lat"]]["warm"]["95"],
            }
        )
    for run in ARMS:
        s = est_js["strategies"][run.key]
        pts.append(
            {
                "key": run.key,
                "phase": "Part A",
                "local": False,
                "joint": s["joint"],
                "cost_1k": {x: 1000 * v for x, v in s["cost_observed_per_case"].items()},
                "p95": lat_a[run.lat.split("-")[1]]["warm"]["95"],
            }
        )
    dist = []
    for s in LAT_1_LOCAL:
        dist.append(
            {
                "label": LAT_LABEL[s],
                "window": "phase 1",
                "local": True,
                "warm": list(lat_1[s]["warm_by_case"].values()),
                "cold": lat_1[s]["cold_ms"],
            }
        )
    for s in LAT_1_ANCHORS:
        dist.append(
            {
                "label": LAT_LABEL[s],
                "window": "phase 1",
                "local": False,
                "warm": list(lat_1[s]["warm_by_case"].values()),
                "cold": lat_1[s]["cold_ms"],
            }
        )
    for s in LAT_A:
        dist.append(
            {
                "label": LAT_LABEL[s],
                "window": "Part A",
                "local": False,
                "warm": list(lat_a[s]["warm_by_case"].values()),
                "cold": lat_a[s]["cold_ms"],
            }
        )
    return {"points": pts, "latency": dist}


def run_figures(fd: dict[str, Any]) -> list[str]:
    import matplotlib.pyplot as plt
    from final_common import TEXT, TEXT2
    from final_figures import _labels, _save

    loc_c, man_c = "#1baf7a", "#eb6834"
    out: list[str] = []

    def legend(ax: Any) -> None:
        h = [
            plt.Line2D(
                [], [], color=loc_c, marker="o", ls="none", mfc="none", ms=7, label="local, phase 1"
            ),
            plt.Line2D(
                [],
                [],
                color=man_c,
                marker="o",
                ls="none",
                mfc="none",
                ms=7,
                label="managed / API, phase 1",
            ),
            plt.Line2D(
                [], [], color=man_c, marker="D", ls="none", ms=7, label="managed, Part A (new)"
            ),
        ]
        ax.legend(handles=h, loc="lower right", fontsize=8)

    def point(ax: Any, p: dict[str, Any], x: float, xerr: Any) -> None:
        j = p["joint"]
        new = p["phase"] == "Part A"
        col = loc_c if p["local"] else man_c
        ax.errorbar(
            x,
            100 * j["point"],
            yerr=[[100 * (j["point"] - j["lo"])], [100 * (j["hi"] - j["point"])]],
            xerr=xerr,
            fmt="D" if new else "o",
            color=col,
            mfc=col if new else "none",
            ms=7,
            mew=1.4,
            elinewidth=0.9,
        )

    # 1. accuracy x p95
    fig, ax = plt.subplots(figsize=(9, 5.6))
    lab = []
    for p in fd["points"]:
        p95 = p["p95"]
        x = max(p95["point"], 0.05)
        point(ax, p, x, [[max(x - max(p95["lo"], 0.05), 0)], [max(p95["hi"] - x, 0)]])
        lab.append((x, 100 * p["joint"]["point"], p["key"]))
    ax.set_xscale("log")
    _labels(ax, lab)
    lo, hi = ax.get_xlim()
    for slo in (50, 500, 2000, 10000):
        if lo <= slo <= hi:
            ax.axvline(slo, color=TEXT2, lw=0.8, ls=":")
            ax.text(slo, ax.get_ylim()[1], f" {slo:g} ms", fontsize=7, color=TEXT2, va="top")
    ax.set_xlabel("warm p95 routing latency, ms (log; 95% CI) — phase-1 and Part-A windows differ")
    ax.set_ylabel("joint accuracy % on test-v2 (ITT, 95% CI)")
    ax.set_title("Accuracy vs p95 latency: phase-1 arms + Part-A managed arms")
    legend(ax)
    _save(fig, "final-a-accuracy-latency-p95.png", out)

    # 2. cost x accuracy
    free_x = 1e-4
    fig, ax = plt.subplots(figsize=(9, 5.6))
    lab = []
    for p in fd["points"]:
        c = p["cost_1k"]
        x = c["point"]
        xs = free_x if x <= 0 else x
        point(ax, p, xs, None if x <= 0 else [[x - c["lo"]], [c["hi"] - x]])
        lab.append((xs, 100 * p["joint"]["point"], p["key"]))
    ax.set_xscale("log")
    ax.set_xlim(free_x / 2, 30)
    _labels(ax, lab)
    ax.axvline(free_x * 2.2, color=TEXT2, lw=0.8, ls=":")
    ax.text(
        free_x,
        ax.get_ylim()[0],
        " US$ 0\n (local)",
        fontsize=7,
        color=TEXT2,
        va="bottom",
        ha="center",
    )
    ax.set_xlabel("routing cost, US$ per 1 000 cases (observed regime, log; 95% CI)")
    ax.set_ylabel("joint accuracy % on test-v2 (ITT, 95% CI)")
    ax.set_title("Cost vs accuracy: phase-1 arms + Part-A managed arms")
    legend(ax)
    _save(fig, "final-a-cost-accuracy.png", out)

    # 3. latency distribution, managed vs local
    dist = fd["latency"]
    fig, ax = plt.subplots(figsize=(10, 5))
    bp = ax.boxplot(
        [np.maximum(np.asarray(d["warm"]), 0.01) for d in dist],
        whis=(5, 95),
        showfliers=True,
        patch_artist=True,
        widths=0.55,
        flierprops={"marker": ".", "markersize": 3, "markeredgecolor": TEXT2},
    )
    for patch, d in zip(bp["boxes"], dist, strict=True):
        patch.set_facecolor(loc_c if d["local"] else man_c)
        patch.set_edgecolor(TEXT)
        if d["window"] == "phase 1":
            patch.set_hatch("///")
            patch.set_alpha(0.75)
    for med in bp["medians"]:
        med.set_color(TEXT)
    for i, d in enumerate(dist, start=1):
        ax.scatter(
            [i + 0.32] * len(d["cold"]),
            np.maximum(d["cold"], 0.01),
            marker="x",
            color=TEXT,
            s=14,
            lw=1,
            zorder=3,
        )
    ax.set_yscale("log")
    ax.set_xticks(
        range(1, len(dist) + 1),
        [f"{d['label']}\n({d['window']})" for d in dist],
        rotation=35,
        ha="right",
        fontsize=7.5,
    )
    ax.set_ylabel("routing latency per case, ms (log)")
    ax.set_title(
        "Latency: managed (Part A) vs local (phase 1) — warm box IQR, whiskers p5-p95; x = cold first case"
    )
    h = [
        plt.Rectangle((0, 0), 1, 1, color=loc_c),
        plt.Rectangle((0, 0), 1, 1, color=man_c),
        plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor=TEXT, hatch="///"),
        plt.Line2D([], [], marker="x", color=TEXT, ls="none"),
    ]
    ax.legend(
        h,
        ["local", "managed / API", "phase-1 window", "cold first case of a block"],
        fontsize=7.5,
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
    )
    ax.set_xlabel(
        "Different time windows: local = phase-1 blocks (same Mac, M5 Pro 48 GB); managed = Part-A blocks (Bedrock sa-east-1 / "
        "OpenRouter from that Mac). Anchor drift (Jev, Haiku) in estimation.md §G3; reported, never subtracted.",
        fontsize=7,
        color=TEXT2,
    )
    _save(fig, "final-a-latency-distribution.png", out)
    return out


def figures_step() -> list[str]:
    fd = json.loads((OUT / "estimation.json").read_text(encoding="utf-8"))["figure_data"]
    if importlib.util.find_spec("matplotlib") is not None:
        return run_figures(fd)
    res = subprocess.run(
        [
            "uv",
            "run",
            "--with",
            "matplotlib",
            "python",
            str(Path(__file__).resolve()),
            "--figures-only",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        print(res.stdout[-2000:], res.stderr[-2000:])
        raise SystemExit("figure step failed")
    return [ln for ln in res.stdout.splitlines() if ln.endswith(".png")]


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-figures", action="store_true")
    ap.add_argument("--figures-only", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.figures_only:
        for p in run_figures(
            json.loads((OUT / "estimation.json").read_text(encoding="utf-8"))["figure_data"]
        ):
            print(p)
        return
    audit = check_provenance()
    ctx = load_ctx()
    prim_lines, prim = family_a(ctx, audit)
    write(OUT / "primary.md", "\n".join(prim_lines))
    write_json(OUT / "primary.json", prim)
    print("family A done", flush=True)

    lat_a = {s: lat_summary(f"a-{s}") for s in LAT_A}
    lat_1 = {s: lat_summary(s) for s in LAT_1_LOCAL + LAT_1_ANCHORS}
    p1 = phase1_context(ctx, lat_1)
    est: dict[str, Any] = {}
    lines = [
        "# Part A estimation tables (ESTIMATION ONLY: prereg-v2a §3 'Estimation only'; CIs, no tests)",
        "",
        "Generated by `scripts/analysis/addendum_a.py`. ITT; 95% CIs = cluster bootstrap over case ids (10k, seed 20260930). The "
        "confirmatory family A is in primary.md. Arms: the six Part-A managed routers (test-v2, 349 cases, 1 rep) and the re-used "
        "phase-1 local references E6b, E3, E10 (same 349 cases; read-only).",
        "",
    ]
    for name, fn in (
        ("strategies", lambda: strategies(ctx)),
        ("deltas", lambda: est_deltas(ctx)),
        ("calibration", lambda: calibration_table(ctx)),
        ("errors", lambda: errors_parse(ctx)),
        ("flips", lambda: flips(ctx)),
        ("latency", lambda: latency(lat_a, lat_1)),
        ("cohere_region", cohere_region),
    ):
        md, js = fn()
        if name == "calibration":
            md = _retitle(
                _retitle(md, "## B. Calibration", "## D. Calibration"),
                "## C. Selective",
                "## D2. Selective",
            )
        lines += md
        est[name] = js
        print(f"  estimation: {name} done", flush=True)
    est["latency"]["summary"] = {
        **{f"a-{s}": {k: v for k, v in lat_a[s].items() if k != "warm_by_case"} for s in LAT_A},
        **{
            s: {k: v for k, v in lat_1[s].items() if k != "warm_by_case"}
            for s in LAT_1_LOCAL + LAT_1_ANCHORS
        },
    }
    est["figure_data"] = figure_data(ctx, est, lat_a, lat_1, p1)
    write(OUT / "estimation.md", "\n".join(lines))
    write_json(OUT / "estimation.json", est)
    ent_md, ent = enterprise(prim, est, lat_a, lat_1, p1)
    write(OUT / "enterprise_matrix.md", ent_md)
    write_json(OUT / "enterprise_matrix.json", ent)
    print("enterprise matrix done", flush=True)
    figs = [] if args.no_figures else figures_step()
    for p in sorted(OUT.iterdir()):
        print(f"  {p}")
    for f in figs:
        print(f"  {f}")


if __name__ == "__main__":
    main()
