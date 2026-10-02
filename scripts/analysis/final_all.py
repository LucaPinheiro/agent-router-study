# ruff: noqa: E501  (report prose and table rows)
"""Regenerate the whole final test-v2 analysis, idempotently, from results/rescored/.

Usage: uv run python scripts/analysis/final_all.py [--no-figures] [--no-study-report]

Reads only (never writes) results/rescored/, results/final/run-manifest.log, config/, docs/results/.
Writes:
  results/analysis/{primary,secondary,estimation,enterprise_matrix}.{md,json}
  results/analysis/study_report_test_v2.md      (`study report --manifest ... --split test_v2`)
  results/analysis/runs_status.md               (which manifest runs are in / still missing)
  results/analysis/exploratory_e2e.{md,json}     (EXPLORATORY: D-002 full-skill e2e + e2e error analysis)
  estudos/figuras/final-*.png                   (matplotlib; see below)
  docs/results/final/*.md + *.json              (committed copies; results/ is gitignored)

Runs that are not COMPLETE in the manifest log (or not rescored yet) are skipped and listed
as missing; re-running after they complete slots them in. Figures need matplotlib, which is
not a project dependency: when it is not importable the figure step re-runs itself through
`uv run --with matplotlib` (an ephemeral overlay; pyproject/uv.lock are untouched).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from final_common import DOCS_OUT, OUT, ROOT, Context, md_table, run_status, write  # noqa: E402

COPY = (
    "primary.md",
    "primary.json",
    "secondary.md",
    "secondary.json",
    "estimation.md",
    "estimation.json",
    "enterprise_matrix.md",
    "enterprise_matrix.json",
    "study_report_test_v2.md",
    "runs_status.md",
    "exploratory_e2e.md",
    "exploratory_e2e.json",
)


def figures_step() -> list[str]:
    if importlib.util.find_spec("matplotlib") is not None:
        from final_exploratory import run_exploratory_figures
        from final_figures import run_figures

        est = json.loads((OUT / "estimation.json").read_text(encoding="utf-8"))
        xjs = json.loads((OUT / "exploratory_e2e.json").read_text(encoding="utf-8"))
        return run_figures(est) + run_exploratory_figures(xjs)
    print(
        "  matplotlib not in the project env: running the figure step via `uv run --with matplotlib`",
        flush=True,
    )
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


def study_report() -> None:
    res = subprocess.run(
        [
            "uv",
            "run",
            "study",
            "report",
            "--manifest",
            "config/study_manifest.yaml",
            "--split",
            "test_v2",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    body = (
        res.stdout
        if res.returncode == 0
        else f"`study report` exited {res.returncode}\n\n```\n{res.stderr[-4000:]}\n```\n"
    )
    write(
        OUT / "study_report_test_v2.md",
        "# `uv run study report --manifest config/study_manifest.yaml --split test_v2`\n\n" + body,
    )


def runs_status() -> None:
    from routing_study.eval.manifest import load_manifest

    m = load_manifest(ROOT / "config" / "study_manifest.yaml")
    st = run_status()
    rows = []
    for r in m.runs:
        rescored = (ROOT / "results" / "rescored" / f"{r.name}.jsonl").exists()
        rows.append(
            [
                r.name,
                st.get(r.name, "not started"),
                "yes" if rescored else "no",
                "analysed" if rescored and st.get(r.name) == "COMPLETE" else "pending",
            ]
        )
    write(
        OUT / "runs_status.md",
        "# Manifest run status at analysis time\n\n"
        + "\n".join(md_table(["run", "log status", "rescored", "in analysis"], rows)),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-figures", action="store_true")
    ap.add_argument("--no-study-report", action="store_true")
    ap.add_argument("--figures-only", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.figures_only:
        from final_exploratory import run_exploratory_figures
        from final_figures import run_figures

        figs = run_figures(json.loads((OUT / "estimation.json").read_text(encoding="utf-8")))
        figs += run_exploratory_figures(
            json.loads((OUT / "exploratory_e2e.json").read_text(encoding="utf-8"))
        )
        for p in figs:
            print(p)
        return
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    from final_enterprise import run_enterprise
    from final_estimation import run_estimation
    from final_exploratory import run_exploratory
    from final_primary import run_primary, run_secondary

    ctx = Context.load()
    print(
        f"loaded {len(ctx.routing)} routing + {len(ctx.e2e)} e2e runs; missing: {', '.join(ctx.missing) or 'none'}",
        flush=True,
    )
    runs_status()
    run_primary(ctx)
    print("primary done", flush=True)
    run_secondary(ctx)
    print("secondary done", flush=True)
    est = run_estimation(ctx)
    run_enterprise(est)
    print("enterprise matrix done", flush=True)
    run_exploratory(ctx)
    print("exploratory (D-002 + e2e error analysis) done", flush=True)
    if not args.no_study_report:
        study_report()
        print("study report done", flush=True)
    figs = [] if args.no_figures else figures_step()
    DOCS_OUT.mkdir(parents=True, exist_ok=True)
    for name in COPY:
        if (OUT / name).exists():
            shutil.copy2(OUT / name, DOCS_OUT / name)
    print("\nwrote:")
    for name in COPY:
        if (OUT / name).exists():
            print(f"  {OUT / name}  (copy: {DOCS_OUT / name})")
    for f in figs:
        print(f"  {f}")
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
