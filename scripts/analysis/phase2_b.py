# ruff: noqa: E501  (report prose and table rows)
"""Part B (large catalog, prereg-v2) analysis: offline, idempotent, written BEFORE any test-L row.

Usage:
  uv run python scripts/analysis/phase2_b.py --manifest config/study_manifest_l.yaml
  uv run python scripts/analysis/phase2_b.py --smoke --split dev_l \\
      --run e2e:E0=dev-l-e2e-e0-native-r1 --run e2e:E9=dev-l-e2e-e9-r1 \\
      --run routing:E9=results/rescored/warm-dev-l-shadow-r1.jsonl

Inputs (read only): `results/rescored/` (legacy scorer of record, e0eef1fb0073: routing primary
and the e2e sensitivity), `results/rescored-sym/` (`eval/scorers_sym.py`: the e2e primary), the
manifest and its log `results/manifest-<stem>.log` (a run is analysed only when COMPLETE), the
phase-1 / Part-A test-v2 rescored files (catalog-size X1 only), `data/dataset_<split>.jsonl`.

Outputs: `docs/results/phase2-b/{primary,secondary,estimation,catalog_size}.{md,json}` and
`estudos/figuras/final-b-*.png`. With `--smoke` everything goes to
`results/phase2l/analysis_smoke/` (figures in its `figures/`) and every page is labelled SMOKE.

prereg-v2 §9 names `final_l_all.py` / `docs/results/phase2/`; the task that wrote this script
named it `phase2_b.py` / `docs/results/phase2-b/` (naming only). Hypotheses follow the draft
§3 with the binding constraint update of 2026-10-02: no local model runs, so H2-L is
Ministral (E6m) vs Haiku 4.5 (E6), NI 3 pp; S5 (Cohere vs LOCAL embedding) and S6 (Nemotron vs
LOCAL Qwen3-8B) have no possible reference arm and are reported as dropped (out of their Holm
family). Statistics are the phase-1 machinery unchanged (`routing_study.eval.stats`): ITT,
per-case means over reps, paired cluster bootstrap over case ids, 10 000 resamples, seed
20260930, sign-flip p (NI: shift +margin, one-sided), TOST by the 90% CI rule.

Holm rule for incomplete runs: a hypothesis whose run is missing or not COMPLETE is reported as
NOT RUN (never imputed) and enters its Holm family with p = 1, so the family size stays the
pre-registered one (conservative). Hypotheses structurally impossible under the constraint
update (S5, S6) are out of the family.

Provenance (fails loudly, SystemExit): every row's catalog, scorer, prompt and dataset hashes;
the provenance header's scorer / dataset / tools sha; one config hash per file (and the
manifest's frozen one); legacy and sym files of an e2e run rescored from the same raw bytes; the
dataset file, the scorer code and (non-smoke) the manifest bytes against the frozen values.
Fields marked TBD@freeze must be filled when prereg-v2 is tagged; a None one aborts a
non-smoke run.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dataset"))

from final_common import (  # noqa: E402
    CATEGORIES,
    ROOT,
    Context,
    Run,
    by_case,
    ci_json,
    fms,
    fmt,
    fnum,
    itt_keys,
    md_table,
    paired_ratio,
    prefix_sizes,
    resample_idx,
    row_list_uncached,
    write,
    write_json,
)

from routing_study.eval.report import itt  # noqa: E402
from routing_study.eval.rescore import read_rescored  # noqa: E402
from routing_study.eval.scorers import business_calls  # noqa: E402
from routing_study.eval.stats import (  # noqa: E402
    BOOT_N,
    BOOT_SEED,
    Contrast,
    bootstrap_mean,
    bootstrap_stat,
    evaluate_contrasts,
    holm,
    paired_delta,
)

RESCORED = ROOT / "results" / "rescored"
RESCORED_SYM = ROOT / "results" / "rescored-sym"
EXP_L = ROOT / "config" / "experiments_l"
EXP_S = ROOT / "config" / "experiments"
OUT = ROOT / "docs" / "results" / "phase2-b"
FIG = ROOT / "estudos" / "figuras"
SMOKE_OUT = ROOT / "results" / "phase2l" / "analysis_smoke"

# ------------------------------------------------------------------ frozen values (prereg-v2 §1)

CATALOG_L = "bc7cd75fce87"  # large profile (confirmed at freeze: served on :8766, 2026-10-02)
CATALOG_S = "128584617807"  # small profile (phase 1, unchanged)
SCORER = "e0eef1fb0073"  # legacy scorer of record (routing primary; e2e sensitivity)
SCORER_SYM = "5ad0f65296e4"  # scorers_sym.py (e2e primary) (confirmed at freeze)
PROMPT = "c61ad0a7b7f8"  # P0, no template change
TOOLS_SHA = {  # tools/list snapshots the rescore scores against
    "large": "a0583726a351a862494c0f655b409c592e48c9a2f1c31ef43371b7ff63a88f07",
    "small": "a9776477226c398702032f7fdd05223fc0a013dfc68ebe0e8f749567e27aa123",
}
DATASET_SHA: dict[str, str | None] = {
    "dev_l": "b02b3722f5c4e434dd97a4c6a4811ac18a1fd1945784a6375639acd0b376e238",
    "test_l": "ae21a5dbce16eb90278612f7dbcf875cb6610b7b12a49cb6f7f57e503d680ff2",  # e1e8683
    "test_v2": "6637c4795b2340b953ac5867498c1aeba7953fea25d76b8614de265cf2902a66",
}
MANIFEST_L_SHA: str | None = (
    "788fac3665ba82e06703a644f42e753f1413441dcc8d3395071d6d8ce8bc2e6b"  # study_manifest_l.yaml
)
DEV_FIXED_L: dict[str, float | None] = {"E1": 0.827}  # S3: regex dev-L CV joint
S7_PROBE = "E10"  # S7: the only large-profile probe (Titan v2; E10c not run), frozen
S2_MIN_N = 60  # OQ-2: below this the same-calls subset is estimation only (frozen)
NI_MARGIN = 0.03
ALPHA = 0.05
LARGE_SPLITS = ("dev_l", "test_l")

# ------------------------------------------------------------------ run registry (test-L names)

ROUTING_L = [
    Run("E1", "l-e1-regex-routing-r1", "E1 regex", "lexical", lat="regex"),
    Run("E2", "l-e2-bm25-routing-r1", "E2 BM25", "lexical", lat="bm25"),
    Run(
        "E3",
        "l-e3-embedding-routing-r1",
        "E3 embedding (Bedrock Titan v2)",
        "managed-semantic",
        lat="embedding",
        local=False,
    ),
    Run(
        "E3c",
        "l-e3c-cohere-routing-r1",
        "E3c Cohere Embed v4",
        "managed-semantic",
        lat="e3c",
        local=False,
    ),
    Run(
        "E3t", "l-e3t-titan-routing-r1", "E3t Titan v2", "managed-semantic", lat="e3t", local=False
    ),
    Run(
        "E10",
        "l-e10-classifier-routing-r1",
        "E10 probe (Bedrock vectors)",
        "managed-semantic",
        lat="classifier",
        local=False,
    ),
    Run(
        "E10c",
        "l-e10c-cohere-routing-r1",
        "E10c probe on Cohere vectors",
        "managed-semantic",
        local=False,
    ),
    Run(
        "E11",
        "l-e11-hybrid-routing-r1",
        "E11 hybrid regex+probe",
        "managed-semantic",
        lat="hybrid",
        local=False,
    ),
    Run(
        "E4",
        "l-e4-jev-canonical-routing-r3",
        "E4 Jev",
        "api-llm",
        "confirmatory (H3-L)",
        lat="jev",
        local=False,
    ),
    Run(
        "E6",
        "l-e6-haiku-canonical-routing-r1",
        "E6 Haiku 4.5",
        "api-llm",
        "confirmatory (H2-L, H3-L)",
        lat="haiku",
        local=False,
    ),
    Run(
        "E6m",
        "l-e6m-ministral-canonical-routing-r1",
        "E6m Ministral 3 8B",
        "api-llm",
        "confirmatory (H2-L)",
        lat="e6m",
        local=False,
    ),
    Run(
        "E6n",
        "l-e6n-nemotron-canonical-routing-r1",
        "E6n Nemotron Nano 9B v2",
        "api-llm",
        lat="e6n",
        local=False,
    ),
    Run("E7", "l-e7-tuned-routing-r3", "E7-L regex->Jev", "cascade", lat="e7", local=False),
    Run("E9", "l-e9-tuned-routing-r3", "E9-L regex->Jev->Sonnet", "cascade", lat="e9", local=False),
    Run(
        "E12",
        "x-l-e12-hybrid-tuned-routing-r3",
        "E12-L hybrid->Jev->Sonnet (exploratory)",
        "cascade",
        "exploratory",
        local=False,
    ),
]
E2E_L = [
    Run(
        "E0",
        "l-e0-native-e2e-r1",
        "E0-L native (no router)",
        "native",
        "confirmatory (H1-L)",
        local=False,
    ),
    Run(
        "E9",
        "l-e9-tuned-e2e-r1",
        "E9-L regex->Jev->Sonnet",
        "cascade",
        "confirmatory (H1-L)",
        local=False,
    ),
    Run(
        "E9-full",
        "l-e9-fullskill-e2e-r1",
        "E9-L all skill tools",
        "cascade",
        "secondary (S1)",
        local=False,
    ),
]
VARIANCE_L = {"E0": "l-e0-native-e2e-rep2-60", "E9": "l-e9-tuned-e2e-rep2-60"}
REPEATS_L = {
    "E1": ("l-e1-regex-routing-repeat20", "E1 regex (20 cases x 2)"),
    "E6": ("l-e6-haiku-canonical-rep2-60", "E6 Haiku 4.5 (60 cases x 2)"),
    "E6m": ("l-e6m-ministral-canonical-repeat50", "E6m Ministral 3 8B (50 cases x 2)"),
    "E6n": ("l-e6n-nemotron-canonical-repeat50", "E6n Nemotron 9B (50 cases x 2)"),
}
LAT_L = [
    "regex",
    "bm25",
    "embedding",
    "e3c",
    "e3t",
    "classifier",
    "hybrid",
    "jev",
    "haiku",
    "e6m",
    "e6n",
    "e7",
    "e9",
]
X2_KEYS = ["E1", "E2", "E3", "E10", "E11", "E4", "E6m", "E6"]
NOT_RUN_REASON = {
    "E3-local": "no local model in phase 2 (constraint 2026-10-02): no local embedding arm on test-L",
    "E6b": "no local model in phase 2 (constraint 2026-10-02): no Qwen3-8B arm on test-L",
}
# X1: the test-v2 run of the same strategy (phase 1 or Part A; same embedder where it matters)
X1_ROUTING = {
    "E1": "v2-e1-regex-routing-r1",
    "E2": "v2-e2-bm25-routing-r1",
    "E3": "v2a-e3t-titan-routing-r1",  # E3-L runs on Titan v2 (experiments_l)
    "E3c": "v2a-e3c-cohere-routing-r1",
    "E3t": "v2a-e3t-titan-routing-r1",
    "E10": "v2a-e10t-titan-routing-r1",
    "E10c": "v2a-e10c-cohere-routing-r1",
    "E11": "v2-e11-hybrid-routing-r1",  # phase-1 hybrid used the LOCAL probe: embedder differs
    "E4": "v2-e4-jev-canonical-routing-r3",
    "E6": "v2-e6-haiku-canonical-routing-r1",
    "E6m": "v2a-e6m-ministral-canonical-routing-r1",
    "E6n": "v2a-e6n-nemotron-canonical-routing-r1",
    "E7": "v2-e7-tuned-routing-r3",
    "E9": "v2-e9-tuned-routing-r3",
}
X1_E2E = {
    "E0": "v2-e0-native-e2e-r1",
    "E9": "v2-e9-tuned-e2e-r1",
    "E9-full": "x-e9-fullskill-e2e-r1",
}

PRIMARY = [
    ("H1-L", Contrast("E9@e2e", "E0@e2e", "H-L", "two_sided")),
    ("H2-L", Contrast("E6m", "E6", "H-L", "non_inferiority", NI_MARGIN)),
    ("H3-L", Contrast("E4", "E6", "H-L", "non_inferiority", NI_MARGIN)),
]
S_E2E = [
    ("S1", Contrast("E9-full@e2e", "E9@e2e", "S-e2e", "greater")),
    ("S2", Contrast("E9@e2e#same", "E0@e2e#same", "S-e2e", "equivalence", NI_MARGIN)),
]
S_ROUTING = [
    ("S4", Contrast("E3", "E1", "S-routing", "two_sided")),
    ("S5", Contrast("E3c", "E3-local", "S-routing", "two_sided")),
    ("S6", Contrast("E6n", "E6b", "S-routing", "non_inferiority", NI_MARGIN)),
    ("S7", Contrast(S7_PROBE, "E4", "S-routing", "two_sided")),
]
S_DROPPED = {"S5", "S6"}  # reference arm is local: impossible under the constraint update

CAVEAT_X = (
    "**Caveat (mandatory, prereg-v2 §3 X1):** the datasets differ: different cases, label sets and catalog text. They "
    "share the generator family, the category proportions and the dedupe procedure, but case difficulty is not "
    "controlled. Routers are re-tuned per catalog, so Δ measures *system at 18 tools vs system at 62 tools*, not a pure "
    "size effect. Absolute accuracies are not production estimates."
)
CAVEAT_X2 = (
    "**Caveat (X2):** same cases, but each profile has its own tuning (dev vs dev-L) and catalog text; Δ isolates the effect "
    "of the 44 added confusable tools on cases the small catalog can answer, for systems tuned per catalog."
)


# ------------------------------------------------------------------ loading + provenance


@dataclass
class Loaded:
    name: str
    path: Path
    rows: list[dict[str, Any]]
    sym_rows: list[dict[str, Any]] | None = None
    config_hash: str | None = None


@dataclass
class Inputs:
    smoke: bool
    split: str
    routing: dict[str, Loaded] = field(default_factory=dict)
    e2e: dict[str, Loaded] = field(default_factory=dict)
    variance: dict[str, Loaded] = field(default_factory=dict)
    repeat: dict[str, Loaded] = field(default_factory=dict)
    x2: dict[str, Loaded] = field(default_factory=dict)
    lat: dict[str, list[tuple[int, int, dict[str, Any]]]] = field(default_factory=dict)
    x1_routing: dict[str, Loaded] = field(default_factory=dict)
    x1_e2e: dict[str, Loaded] = field(default_factory=dict)
    inventory: list[list[Any]] = field(default_factory=list)
    audit: list[list[Any]] = field(default_factory=list)
    cases: dict[str, dict[str, Any]] = field(default_factory=dict)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen(value: Any, what: str) -> Any:
    if value is None:
        raise SystemExit(f"TBD@freeze: {what} is not filled in scripts/analysis/phase2_b.py")
    return value


def check_rows(
    label: str,
    prov: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    split: str,
    catalog: str,
    sym: bool,
    config_hash: str | None = None,
) -> str:
    """Assert prereg-v2 §1 on one rescored file; return its (single) config hash."""
    want_ds = frozen(DATASET_SHA.get(split), f"DATASET_SHA[{split!r}]")
    profile = "large" if split in LARGE_SPLITS else "small"
    if not rows:
        raise SystemExit(f"{label}: no rows")
    ds = prov.get("dataset") or {}
    if ds.get("split") != split or ds.get("sha256") != want_ds:
        raise SystemExit(f"{label}: provenance dataset {ds} != split {split} sha {want_ds[:12]}")
    if (prov.get("tools") or {}).get("sha256") != TOOLS_SHA[profile]:
        raise SystemExit(
            f"{label}: scored against tools {prov.get('tools')}, expected the {profile} snapshot"
        )
    if sym:
        if prov.get("scorer") != "sym" or prov.get("scorer_hash") != SCORER_SYM:
            raise SystemExit(
                f"{label}: sym file scorer {prov.get('scorer')}/{prov.get('scorer_hash')} != sym/{SCORER_SYM}"
            )
    elif prov.get("scorer", "legacy") != "legacy" or prov.get("scorer_hash") != SCORER:
        raise SystemExit(
            f"{label}: legacy file scorer {prov.get('scorer')}/{prov.get('scorer_hash')} != {SCORER}"
        )
    cfg = {r.get("config_hash") for r in rows}
    if len(cfg) != 1:
        raise SystemExit(f"{label}: rows of several config hashes {sorted(map(str, cfg))}")
    got_cfg = next(iter(cfg))
    if config_hash is not None and got_cfg != config_hash:
        raise SystemExit(f"{label}: config_hash {got_cfg} != manifest {config_hash}")
    for r in rows:
        got = (
            r.get("catalog_hash"),
            r.get("scorer_hash"),
            r.get("prompt_hash"),
            r.get("dataset_sha256"),
            r.get("split"),
        )
        want = (catalog, SCORER, PROMPT, want_ds, split)
        if got != want:
            raise SystemExit(f"hash mismatch in {label} case {r.get('case_id')}: {got} != {want}")
    if len({(r["case_id"], r["rep"]) for r in rows}) != len(rows):
        raise SystemExit(f"{label}: duplicate (case, rep) keys")
    return str(got_cfg)


def _resolve(spec: str) -> Path:
    p = Path(spec)
    if not p.is_absolute():
        p = ROOT / spec
    return p if p.suffix in (".jsonl", ".partial") or p.exists() else RESCORED / f"{spec}.jsonl"


def _sym_path(path: Path) -> Path | None:
    for cand in (
        path.parent.with_name(path.parent.name + "-sym") / path.name,
        RESCORED_SYM / path.name,
    ):
        if cand.exists():
            return cand
    return None


def load_run(
    spec: str, *, split: str, catalog: str, e2e: bool, config_hash: str | None = None
) -> Loaded | None:
    """`spec` = run name (results/rescored/<name>.jsonl), a path, or `legacy|sym` paths (e2e)."""
    legacy_spec, _, sym_spec = spec.partition("|")
    path = _resolve(legacy_spec)
    if not path.exists():
        return None
    prov, rows = read_rescored(path)
    cfg = check_rows(
        path.name, prov, rows, split=split, catalog=catalog, sym=False, config_hash=config_hash
    )
    out = Loaded(path.stem, path, rows, config_hash=cfg)
    if e2e:
        sp = _resolve(sym_spec) if sym_spec else _sym_path(path)
        if sp is not None and sp.exists():
            sprov, srows = read_rescored(sp)
            check_rows(
                sp.name,
                sprov,
                srows,
                split=split,
                catalog=catalog,
                sym=True,
                config_hash=config_hash,
            )
            if sprov["source"]["sha256"] != prov["source"]["sha256"]:
                raise SystemExit(
                    f"{path.name}: legacy and sym files were rescored from different raw files"
                )
            if {(r["case_id"], r["rep"]) for r in srows} != {
                (r["case_id"], r["rep"]) for r in rows
            }:
                raise SystemExit(
                    f"{path.name}: legacy and sym files have different (case, rep) keys"
                )
            out.sym_rows = srows
    return out


def manifest_specs(
    path: Path, smoke: bool
) -> tuple[dict[tuple[str, str], str], dict[str, str], dict[str, str | None]]:
    """(kind, key) -> run name for every registered run that is COMPLETE in the manifest log;
    plus the status and the frozen config hash of every manifest run."""
    from routing_study.eval.manifest import load_manifest

    if not smoke and _sha256(path) != frozen(MANIFEST_L_SHA, "MANIFEST_L_SHA"):
        raise SystemExit(f"{path} sha256 differs from the frozen prereg-v2 value")
    man = load_manifest(path)
    log = ROOT / man.results_dir / f"manifest-{path.stem}.log"
    status: dict[str, str] = {}
    if log.exists():
        pat = re.compile(
            r"^\S+ (COMPLETE|FLAGGED|ABORT\w*|REFUSED|SKIP\w*|RUN|RESCORED|INCOMPLETE|BUDGET) ([^:\s]+)"
        )
        for line in log.read_text(encoding="utf-8").splitlines():
            m = pat.match(line)
            if m and m.group(1) != "RESCORED":
                status[m.group(2)] = m.group(1)
    names = {r.name: r for r in man.runs}
    canon: dict[str, tuple[str, str]] = {}
    canon |= {r.name: ("routing", r.key) for r in ROUTING_L}
    canon |= {r.name: ("e2e", r.key) for r in E2E_L}
    canon |= {n: ("variance", k) for k, n in VARIANCE_L.items()}
    canon |= {n: ("repeat", k) for k, (n, _) in REPEATS_L.items()}
    canon |= {f"l-x2-small-{k.lower()}-routing-r1": ("x2", k) for k in X2_KEYS}
    specs: dict[tuple[str, str], str] = {}
    for name in names:
        st = status.get(name, "not run")
        if name in canon and st == "COMPLETE":
            specs[canon[name]] = name
        m = re.match(r"^lat-l-(\w+)-b[1-4]$", name)
        if m and st == "COMPLETE":
            specs[("lat", m.group(1))] = f"lat-l-{m.group(1)}"
    st_all = {n: status.get(n, "not run") for n in names}
    st_all |= {
        "__unmapped__": ", ".join(n for n in names if n not in canon and not n.startswith("lat-l-"))
        or "-"
    }
    return specs, st_all, {n: r.config_hash for n, r in names.items()}


def load_inputs(args: argparse.Namespace) -> Inputs:
    smoke, split = args.smoke, args.split
    inp = Inputs(smoke=smoke, split=split)
    # static checks: dataset bytes and scorer code
    from routing_study.eval.scorers import scorer_hash
    from routing_study.eval.scorers_sym import scorer_sym_hash

    data = ROOT / "data" / f"dataset_{split}.jsonl"
    want = frozen(DATASET_SHA.get(split), f"DATASET_SHA[{split!r}]")
    if not data.exists() or _sha256(data) != want:
        raise SystemExit(f"{data.name} sha256 differs from the frozen value")
    if scorer_hash() != SCORER or scorer_sym_hash() != SCORER_SYM:
        raise SystemExit(
            f"scorer code changed: legacy {scorer_hash()} (want {SCORER}), sym {scorer_sym_hash()} (want {SCORER_SYM})"
        )
    for name, prof in (("tools_list_large.json", "large"), ("tools_list.json", "small")):
        if _sha256(ROOT / "mcp_server" / name) != TOOLS_SHA[prof]:
            raise SystemExit(f"mcp_server/{name} sha256 differs from the frozen value")
    inp.cases = {
        c["id"]: c for c in map(json.loads, data.read_text(encoding="utf-8").splitlines()) if c
    }
    specs: dict[tuple[str, str], str] = {}
    status: dict[str, str] = {}
    cfg_frozen: dict[str, str | None] = {}
    if args.manifest:
        specs, status, cfg_frozen = manifest_specs(ROOT / args.manifest, smoke)
    for spec in args.run or []:
        m = re.match(r"^(routing|e2e|variance|repeat|x2|lat):([\w-]+)=(.+)$", spec)
        if not m:
            raise SystemExit(
                f"bad --run {spec!r}: kind:KEY=name|path (kind: routing e2e variance repeat x2 lat)"
            )
        specs[(m.group(1), m.group(2))] = m.group(3)
    n_split = len(inp.cases)

    def inv(kind: str, key: str, canonical: str, ld: Loaded | None, note: str = "") -> None:
        if ld is None:
            st = status.get(canonical, "no file") if args.manifest else "not given"
            inp.inventory.append([kind, key, canonical, "-", "-", "-", "-", f"**NOT RUN** ({st})"])
            return
        rs = ld.rows
        n_cases = len({r["case_id"] for r in rs})
        inp.inventory.append(
            [
                kind,
                key,
                ld.path.relative_to(ROOT) if ld.path.is_relative_to(ROOT) else ld.path,
                len(rs),
                f"{n_cases} / {n_split}",
                sum(1 for r in rs if r.get("error")),
                "yes"
                if ld.sym_rows is not None
                else ("n/a" if kind not in ("e2e", "variance") else "**missing**"),
                "used" + (f"; {note}" if note else ""),
            ]
        )
        inp.audit.append(
            [
                ld.path.name,
                ld.config_hash,
                CATALOG_S if kind == "x2" else CATALOG_L,
                SCORER,
                SCORER_SYM if ld.sym_rows is not None else "-",
                PROMPT,
                "ok",
            ]
        )

    def get(kind: str, key: str, canonical: str, *, catalog: str = CATALOG_L) -> Loaded | None:
        spec = specs.get((kind, key))
        ld = None
        if spec is not None:
            ld = load_run(
                spec,
                split=split,
                catalog=catalog,
                e2e=kind in ("e2e", "variance"),
                config_hash=cfg_frozen.get(spec),
            )
            if ld is None:
                raise SystemExit(f"{kind}:{key}: {spec} not found")
        inv(kind, key, canonical, ld)
        return ld

    for r in ROUTING_L:
        if (ld := get("routing", r.key, r.name)) is not None:
            inp.routing[r.key] = ld
    for r in E2E_L:
        if (ld := get("e2e", r.key, r.name)) is not None:
            inp.e2e[r.key] = ld
    for k, n in VARIANCE_L.items():
        if (ld := get("variance", k, n)) is not None:
            inp.variance[k] = ld
    for k, (n, _) in REPEATS_L.items():
        if (ld := get("repeat", k, n)) is not None:
            inp.repeat[k] = ld
    for k in X2_KEYS:
        if (
            ld := get("x2", k, f"l-x2-small-{k.lower()}-routing-r1", catalog=CATALOG_S)
        ) is not None:
            inp.x2[k] = ld
    for s in LAT_L:
        spec = specs.get(("lat", s))
        blocks = []
        if spec is not None:
            for b in (1, 2, 3, 4):
                p = _resolve(f"{spec}-b{b}")
                if not p.exists():
                    continue
                prov, rows = read_rescored(p)
                check_rows(
                    p.name,
                    prov,
                    rows,
                    split=split,
                    catalog=CATALOG_L,
                    sym=False,
                    config_hash=cfg_frozen.get(f"{spec}-b{b}"),
                )
                blocks += [(b, i, r) for i, r in enumerate(rows)]
        if blocks:
            inp.lat[s] = blocks
        inp.inventory.append(
            [
                "lat",
                s,
                f"lat-l-{s}-b1..4",
                len(blocks) or "-",
                "-",
                sum(1 for *_, r in blocks if r.get("error")) if blocks else "-",
                "n/a",
                f"used ({len({b for b, _, _ in blocks})} blocks)" if blocks else "**NOT RUN**",
            ]
        )
    if args.manifest:
        inp.inventory.append(
            [
                "manifest",
                "-",
                f"unmapped runs: {status.get('__unmapped__')}",
                "",
                "",
                "",
                "",
                "ignored",
            ]
        )
    # X1 counterparts on test-v2 (phase 1 / Part A; read only)
    for k in inp.routing:
        if (
            k in X1_ROUTING
            and (ld := load_run(X1_ROUTING[k], split="test_v2", catalog=CATALOG_S, e2e=False))
            is not None
        ):
            inp.x1_routing[k] = ld
    for k in inp.e2e:
        if (
            k in X1_E2E
            and (ld := load_run(X1_E2E[k], split="test_v2", catalog=CATALOG_S, e2e=True))
            is not None
        ):
            inp.x1_e2e[k] = ld
    for ld in [*inp.x1_routing.values(), *inp.x1_e2e.values()]:
        inp.audit.append(
            [
                ld.path.name + " (test-v2, X1)",
                ld.config_hash,
                CATALOG_S,
                SCORER,
                SCORER_SYM if ld.sym_rows is not None else "-",
                PROMPT,
                "ok",
            ]
        )
    return inp


def context(inp: Inputs, runs: Mapping[str, Loaded] | None = None) -> Context:
    ctx = Context()
    reg = {r.key: r for r in ROUTING_L}
    for k, ld in (inp.routing if runs is None else runs).items():
        ctx.routing[k] = ld.rows
        ctx.runs[k] = Run(
            reg[k].key,
            ld.name,
            reg[k].label,
            reg[k].family,
            reg[k].status,
            reg[k].lat,
            reg[k].local,
        )
    reg_e = {r.key: r for r in E2E_L}
    for k, ld in inp.e2e.items():
        ctx.e2e[k] = ld.rows
        ctx.e2e_runs[k] = Run(
            k, ld.name, reg_e[k].label, reg_e[k].family, reg_e[k].status, local=False
        )
    return ctx


# ------------------------------------------------------------------ statistics (pure)


def keyed(
    rows: Sequence[dict[str, Any]], score: str, keep: Callable[[str], bool] | None = None
) -> dict[Hashable, float]:
    """(case, rep) -> ITT score, optionally restricted to the case ids `keep` accepts."""
    return {k: v for k, v in itt_keys(rows, score).items() if keep is None or keep(k[0])}


def primary_scores(
    routing: Mapping[str, Sequence[dict[str, Any]]],
    e2e_sym: Mapping[str, Sequence[dict[str, Any]]],
    *,
    routing_score: str = "joint_correct",
    keep: Callable[[str], bool] | None = None,
) -> dict[str, dict[Hashable, float]]:
    out = {k: keyed(rs, routing_score, keep) for k, rs in routing.items()}
    out |= {f"{k}@e2e": keyed(rs, "e2e_success", keep) for k, rs in e2e_sym.items()}
    return out


def holm_fixed(
    results: list[dict[str, Any]], ids: Sequence[str], dropped: set[str] = frozenset()
) -> None:  # type: ignore[assignment]
    """Holm within the family: a not-run hypothesis enters with p = 1 (family size stays the
    pre-registered one); a structurally dropped one is out of the family."""
    pv = {
        i: (1.0 if "missing" in r or r.get("p") is None else float(r["p"]))
        for i, r in zip(ids, results, strict=True)
        if i not in dropped
    }
    adj = holm(pv)
    for i, r in zip(ids, results, strict=True):
        if i in dropped:
            r["p_holm"], r["reject"] = None, None
        else:
            r["p_holm"] = adj[i]
            r["reject"] = "missing" not in r and adj[i] is not None and adj[i] < ALPHA


def evaluate_family(
    scores: Mapping[str, Mapping[Hashable, float]],
    spec: Sequence[tuple[str, Contrast]],
    dropped: set[str] = frozenset(),  # type: ignore[assignment]
) -> list[dict[str, Any]]:
    res = evaluate_contrasts(scores, [c for _, c in spec])
    holm_fixed(res, [i for i, _ in spec], dropped)
    return res


def verdict_changes(leg: Sequence[dict[str, Any]], sym: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Turns whose e2e verdict differs between the legacy and the symmetric scorer."""
    a = {(r["case_id"], r["rep"]): itt(r, "e2e_success") or 0.0 for r in leg}
    b = {(r["case_id"], r["rep"]): itt(r, "e2e_success") or 0.0 for r in sym}
    keys = a.keys() & b.keys()
    return {
        "turns": len(keys),
        "fail_to_success": sum(1 for k in keys if a[k] < 0.5 <= b[k]),
        "success_to_fail": sum(1 for k in keys if b[k] < 0.5 <= a[k]),
    }


def pair_outcome_changes(run_leg, ref_leg, run_sym, ref_sym) -> int:  # type: ignore[no-untyped-def]
    """Cases whose paired outcome (run-only win / ref-only win / tie) differs between scorers."""

    def outcome(run: Sequence[dict[str, Any]], ref: Sequence[dict[str, Any]]) -> dict[str, int]:
        a = {r["case_id"]: itt(r, "e2e_success") or 0.0 for r in run}
        b = {r["case_id"]: itt(r, "e2e_success") or 0.0 for r in ref}
        return {c: int(a[c] >= 0.5) - int(b[c] >= 0.5) for c in a.keys() & b.keys()}

    x, y = outcome(run_leg, ref_leg), outcome(run_sym, ref_sym)
    return sum(1 for c in x.keys() & y.keys() if x[c] != y[c])


def call_seq(r: dict[str, Any]) -> tuple[str, ...]:
    return tuple(c["name"] for c in business_calls(r))


def same_calls_cases(a: Sequence[dict[str, Any]], b: Sequence[dict[str, Any]]) -> set[str]:
    """Case ids where both runs executed the same sequence of business calls (rep 1)."""
    x = {r["case_id"]: call_seq(r) for r in a if r["rep"] == 1}
    y = {r["case_id"]: call_seq(r) for r in b if r["rep"] == 1}
    return {c for c in x.keys() & y.keys() if x[c] == y[c]}


def indep_delta(
    a: Mapping[str, Sequence[float]], b: Mapping[str, Sequence[float]]
) -> tuple[float, float, float] | None:
    """Unpaired Δ mean(a) − mean(b) with INDEPENDENT cluster bootstraps per split (X1)."""
    if not a or not b:
        return None
    rng_a, rng_b = np.random.default_rng(BOOT_SEED), np.random.default_rng(BOOT_SEED + 1)

    def boot(
        g: Mapping[str, Sequence[float]], rng: np.random.Generator
    ) -> tuple[float, np.ndarray]:
        keys = sorted(g, key=str)
        s = np.array([float(sum(g[k])) for k in keys])
        n = np.array([len(g[k]) for k in keys], dtype=float)
        idx = rng.integers(0, len(keys), size=(BOOT_N, len(keys)))
        return float(s.sum() / n.sum()), s[idx].sum(axis=1) / n[idx].sum(axis=1)

    pa, ma = boot(a, rng_a)
    pb, mb = boot(b, rng_b)
    lo, hi = np.percentile(ma - mb, [2.5, 97.5])
    return pa - pb, float(lo), float(hi)


def pct_ratio(
    a: Mapping[str, float], b: Mapping[str, float], q: float
) -> tuple[float, float, float, int] | None:
    """Paired (same warm case ids) cluster-bootstrap CI of percentile_q(a) / percentile_q(b)."""
    keys = sorted(set(a) & set(b), key=str)
    if len(keys) < 2:
        return None
    x = np.array([a[k] for k in keys])
    y = np.array([b[k] for k in keys])
    idx = resample_idx(len(keys))
    r = np.percentile(x[idx], q, axis=1) / np.maximum(np.percentile(y[idx], q, axis=1), 1e-12)
    lo, hi = np.percentile(r, [2.5, 97.5])
    return float(np.percentile(x, q) / np.percentile(y, q)), float(lo), float(hi), len(keys)


def h1l(
    e9_sym: Sequence[dict[str, Any]],
    e0_sym: Sequence[dict[str, Any]],
    e9_leg: Sequence[dict[str, Any]],
    e0_leg: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """H1-L alone (no Holm partners): sym Δ, legacy sensitivity Δ, cost-ratio co-primary and the
    verdict-change counts. The report uses the same functions inside the H1-H3 Holm family."""
    sym = evaluate_contrasts(
        {"E9@e2e": keyed(e9_sym, "e2e_success"), "E0@e2e": keyed(e0_sym, "e2e_success")},
        [PRIMARY[0][1]],
    )[0]
    leg = evaluate_contrasts(
        {"E9@e2e": keyed(e9_leg, "e2e_success"), "E0@e2e": keyed(e0_leg, "e2e_success")},
        [PRIMARY[0][1]],
    )[0]
    cost = paired_ratio(
        by_case(e9_leg, lambda r: (r.get("cost_usd") or {}).get("total")),
        by_case(e0_leg, lambda r: (r.get("cost_usd") or {}).get("total")),
    )
    return {
        "sym": sym,
        "legacy": leg,
        "cost_ratio": cost,
        "verdict_changes": {
            "E9": verdict_changes(e9_leg, e9_sym),
            "E0": verdict_changes(e0_leg, e0_sym),
        },
        "pair_outcome_changes": pair_outcome_changes(e9_leg, e0_leg, e9_sym, e0_sym),
    }


# ------------------------------------------------------------------ report helpers


def banner(inp: Inputs) -> list[str]:
    if not inp.smoke:
        return []
    return [
        f"> **SMOKE RUN on `{inp.split}` — NOT A RESULT.** This page exercises the frozen Part-B analysis code on the dev-L "
        "tuning split, with whatever dev-L runs exist. dev-L is where every router was tuned (in-sample), arms are missing, "
        "n is small and `routing:E9` is the dev-L shadow pass (cascade decision with shadow decisions recorded). No number "
        "here may be quoted as a Part-B estimate.",
        "",
    ]


def ctable(
    results: list[dict[str, Any]], ids: Sequence[str], dropped: set[str] = frozenset()
) -> tuple[list[list[Any]], list[dict[str, Any]]]:  # type: ignore[assignment]
    from final_primary import _contrast_rows

    table, js = _contrast_rows(results, list(ids))
    for row, j, res, i in zip(table, js, results, ids, strict=True):
        row[1], row[2] = str(row[1]).split("#")[0], str(row[2]).split("#")[0]
        if "missing" in res:
            miss = str(res["missing"]).split("#")[0].replace("@e2e", "")
            why = NOT_RUN_REASON.get(miss, "run missing or not COMPLETE")
            row[5] = f"missing {miss}: {why}"
            row[-1] = (
                "**DROPPED** (constraint update; out of the Holm family)"
                if i in dropped
                else "**NOT RUN** (enters Holm with p = 1)"
            )
            j["verdict"] = row[-1]
            j["reason"] = why
        elif res["contrast"].kind == "two_sided":
            lo, hi = res["delta_ci"][1], res["delta_ci"][2]
            if hi < 0 or lo > 0:
                row[-1] = j["verdict"] = row[-1] + (" (run lower)" if hi < 0 else " (run higher)")
        if i in dropped:
            row[8] = row[9] = "-"
    return table, js


HDR = [
    "id",
    "run",
    "reference",
    "kind",
    "n cases",
    "Δ pp [95% CI] (paired cluster bootstrap)",
    "McNemar case-level run-only/ref-only",
    "sign-flip p",
    "Holm p (family)",
    "reject @0.05",
    "verdict",
]


def per1k(rows: Sequence[dict[str, Any]] | None, f: str) -> tuple[float, float, float] | None:
    if not rows:
        return None
    ci = bootstrap_mean(by_case(rows, lambda r: (r.get("cost_usd") or {}).get(f)))
    return None if ci is None else (1000 * ci[0], 1000 * ci[1], 1000 * ci[2])


def lat_summary(rows: list[tuple[int, int, dict[str, Any]]]) -> dict[str, Any]:
    """Warm (not the first case of a block, error-free) and cold routing latency of a benchmark."""
    warm = {
        r["case_id"]: float(r["latency_ms"]["routing"])
        for _, i, r in rows
        if i > 0 and not r.get("error")
    }
    cold = [float(r["latency_ms"]["routing"]) for _, i, r in rows if i == 0]
    groups = {c: [v] for c, v in warm.items()}
    pct = {
        q: bootstrap_stat(groups, lambda a, q=q: float(np.percentile(a, q))) if warm else None
        for q in (50, 95)
    }
    return {
        "blocks": sorted({b for b, _, _ in rows}),
        "n_warm": len(warm),
        "n_cold": len(cold),
        "errors": sum(1 for _, _, r in rows if r.get("error")),
        "warm": {str(q): ci_json(v) for q, v in pct.items()},
        "cold_ms": cold,
        "warm_by_case": dict(sorted(warm.items())),
    }


def _ci3(d: dict[str, float] | None) -> list[float] | None:
    return None if d is None else [d["point"], d["lo"], d["hi"]]


# ------------------------------------------------------------------ primary


def primary(inp: Inputs, lat: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    routing = {k: ld.rows for k, ld in inp.routing.items()}
    e2e_sym = {k: ld.sym_rows for k, ld in inp.e2e.items() if ld.sym_rows is not None}
    e2e_leg = {k: ld.rows for k, ld in inp.e2e.items()}
    ids = [i for i, _ in PRIMARY]
    out: dict[str, Any] = {
        "status": "CONFIRMATORY (prereg-v2 Part B, Holm across H1-L..H3-L, alpha 0.05)"
        + (" — SMOKE, NOT A RESULT" if inp.smoke else ""),
        "split": inp.split,
        "smoke": inp.smoke,
    }
    lines = banner(inp) + [
        f"# Part B primary analysis [C]: H1-L, H2-L, H3-L on `{inp.split}`",
        "",
        "Generated by `scripts/analysis/phase2_b.py` (offline). ITT (an infra or parse failure is wrong); unit = case, reps averaged "
        "first; paired cluster bootstrap over case ids, 10 000 resamples, seed 20260930; p = case-level sign-flip (NI: shift +3 pp, "
        "one-sided); Holm step-down across H1-L..H3-L (α 0.05). A hypothesis whose run is missing or not COMPLETE is **NOT RUN** "
        "(never imputed) and enters Holm with p = 1. Routing joint: legacy scorer e0eef1fb0073; e2e: `e2e_success_sym` "
        f"(scorers_sym {SCORER_SYM}).",
        "",
        "- **H1-L (two-sided, e2e, symmetric scorer):** e2e_success_sym(E9-L) − e2e_success_sym(E0-L); directional claim only if the CI excludes 0.",
        "- **H2-L (NI, 3 pp; re-specified by the constraint update of 2026-10-02):** Joint(E6m Ministral) − Joint(E6 Haiku 4.5) > −3 pp.",
        "- **H3-L (NI, 3 pp):** Joint(E4 Jev) − Joint(E6 Haiku 4.5) > −3 pp.",
        "",
    ]
    res = evaluate_family(primary_scores(routing, e2e_sym), PRIMARY)
    table, js = ctable(res, ids)
    out["itt"] = js
    lines += ["## Primary family: ITT [C]", ""] + md_table(HDR, table)

    # H1-L legacy sensitivity + co-primaries
    lines += ["## H1-L under the legacy asymmetric scorer (SENSITIVITY, not tested) [E]", ""]
    if "E9" in e2e_leg and "E0" in e2e_leg:
        leg = evaluate_contrasts(
            {
                "E9@e2e": keyed(e2e_leg["E9"], "e2e_success"),
                "E0@e2e": keyed(e2e_leg["E0"], "e2e_success"),
            },
            [PRIMARY[0][1]],
        )
        lt, lj = ctable(leg, ["H1-L legacy"])
        for row in lt:
            row[8], row[9] = "- (not tested)", "-"
        vc = {
            k: verdict_changes(e2e_leg[k], e2e_sym[k]) if k in e2e_sym else None
            for k in ("E9", "E0")
        }
        poc = (
            pair_outcome_changes(e2e_leg["E9"], e2e_leg["E0"], e2e_sym["E9"], e2e_sym["E0"])
            if {"E9", "E0"} <= e2e_sym.keys()
            else None
        )
        lines += md_table(HDR, lt)
        lines += md_table(
            ["arm", "turns", "legacy fail → sym success", "legacy success → sym fail"],
            [
                [k, v["turns"], v["fail_to_success"], v["success_to_fail"]]
                if v
                else [k, "sym file missing", "", ""]
                for k, v in vc.items()
            ],
        )
        lines += [
            f"Cases whose paired verdict (E9-L-only win / E0-L-only win / tie) differs between the two scorers: **{'-' if poc is None else poc}**.",
            "",
        ]
        out["h1l_legacy"] = {"contrast": lj[0], "verdict_changes": vc, "pair_outcome_changes": poc}
    else:
        lines += ["**NOT RUN**: E0-L and/or E9-L e2e missing.", ""]
        out["h1l_legacy"] = None

    lines += ["## Co-primary estimates [C]", ""]
    crow = []
    cr = (
        paired_ratio(
            by_case(e2e_leg["E9"], lambda r: (r.get("cost_usd") or {}).get("total")),
            by_case(e2e_leg["E0"], lambda r: (r.get("cost_usd") or {}).get("total")),
        )
        if {"E9", "E0"} <= e2e_leg.keys()
        else None
    )
    crow.append(
        [
            "H1-L co-primary",
            "cost per turn E9-L / E0-L",
            "US$/turn routing + executor, observed regime",
            fmt(per1k(e2e_leg.get("E9"), "total"), 1, 3),
            fmt(per1k(e2e_leg.get("E0"), "total"), 1, 3),
            "**NOT RUN**" if cr is None else f"{cr[0]:.3f} [{cr[1]:.3f}, {cr[2]:.3f}]",
            "-" if cr is None else cr[3],
        ]
    )
    lr = (
        pct_ratio(lat["e6m"]["warm_by_case"], lat["haiku"]["warm_by_case"], 95)
        if {"e6m", "haiku"} <= lat.keys()
        else None
    )
    crow.append(
        [
            "H2-L co-primary",
            "p95 latency E6m / E6 Haiku",
            "warm routing latency, dedicated benchmark (lat-l-*)",
            fms(_ci3(lat.get("e6m", {}).get("warm", {}).get("95"))),
            fms(_ci3(lat.get("haiku", {}).get("warm", {}).get("95"))),
            "**NOT RUN**" if lr is None else f"{lr[0]:.3f} [{lr[1]:.3f}, {lr[2]:.3f}]",
            "-" if lr is None else lr[3],
        ]
    )
    lines += md_table(
        [
            "estimate",
            "ratio",
            "what",
            "numerator (US$/1k or ms) [95% CI]",
            "denominator [95% CI]",
            "ratio [95% CI]",
            "n paired cases",
        ],
        crow,
    )
    out["co_primary"] = {
        "h1l_cost_ratio": None
        if cr is None
        else {"point": cr[0], "lo": cr[1], "hi": cr[2], "n_cases": cr[3]},
        "h2l_p95_ratio": None
        if lr is None
        else {"point": lr[0], "lo": lr[1], "hi": lr[2], "n_cases": lr[3]},
    }

    # sensitivities of the three primaries
    flagged = {
        c for c, x in inp.cases.items() if (x.get("label_audit") or {}).get("decision") == "flagged"
    }
    cat = {c: x["category"] for c, x in inp.cases.items()}
    variants: list[tuple[str, dict[str, dict[Hashable, float]]]] = [
        (
            "first-label joint (H2-L, H3-L)",
            primary_scores(routing, e2e_sym, routing_score="joint_first_label"),
        ),
        (
            "ambiguo excluded",
            primary_scores(routing, e2e_sym, keep=lambda c: cat.get(c) != "ambiguo"),
        ),
        (
            "ambiguo only (reported apart)",
            primary_scores(routing, e2e_sym, keep=lambda c: cat.get(c) == "ambiguo"),
        ),
        (
            f"audit-flagged cases excluded ({len(flagged)} flagged)",
            primary_scores(routing, e2e_sym, keep=lambda c: c not in flagged),
        ),
    ]
    from final_primary import _pairwise_error_free

    ef_ctx = Context(routing=dict(routing), e2e=dict(e2e_sym))
    ef_scores, ef_cs, ef_sizes = _pairwise_error_free(
        primary_scores(routing, e2e_sym), ef_ctx, [c for _, c in PRIMARY]
    )
    srow, sjs = [], []
    for label, sc in variants:
        for i, r in zip(ids, evaluate_contrasts(sc, [c for _, c in PRIMARY]), strict=True):
            srow.append(_sens_row(i, label, r))
            sjs.append(_sens_js(i, label, r))
    for i, r in zip(ids, evaluate_contrasts(ef_scores, ef_cs), strict=True):
        srow.append(_sens_row(i, "error-free cases of both runs", r))
        sjs.append(_sens_js(i, "error-free cases of both runs", r))
    lines += ["## Sensitivities of the primaries (prereg-v2 §3, NOT tested; unadjusted) [E]", ""]
    lines += md_table(["id", "variant", "n cases", "Δ pp [95% CI]", "CI verdict"], srow)
    out["sensitivity"] = sjs

    # headline
    hrow = []
    for k in ("E6m", "E6", "E4"):
        if k in routing:
            hrow.append(
                [
                    k,
                    inp.routing[k].name,
                    "joint (legacy)",
                    len(routing[k]),
                    sum(1 for r in routing[k] if r.get("error")),
                    fmt(bootstrap_mean(by_case(routing[k], lambda r: itt(r, "joint_correct")))),
                ]
            )
    for k in ("E0", "E9"):
        for sc_name, rs in (
            ("e2e_success_sym", e2e_sym.get(k)),
            ("e2e_success legacy", e2e_leg.get(k)),
        ):
            if rs:
                hrow.append(
                    [
                        k + "-L e2e",
                        inp.e2e[k].name,
                        sc_name,
                        len(rs),
                        sum(1 for r in rs if r.get("error")),
                        fmt(bootstrap_mean(by_case(rs, lambda r: itt(r, "e2e_success")))),
                    ]
                )
    lines += ["## Headline per run (ITT, 95% cluster-bootstrap CI) [E]", ""]
    lines += md_table(["arm", "run", "metric", "rows", "error rows", "% [95% CI]"], hrow)
    lines += [
        "## Reading",
        "",
        "- NI decision rule: non-inferior iff the lower bound of the two-sided 95% paired CI of Δ is above −3 pp; the Holm-adjusted "
        "sign-flip p tests H0: Δ ≤ −3 pp. Both are shown; the CI rule is the pre-registered decision.",
        "- H1-L: two-sided; the legacy-scorer number is a sensitivity reported side by side, never the decision.",
        "",
        "## Run inventory and provenance",
        "",
        "Every registered arm; a missing one is reported as NOT RUN. Provenance asserted on every row (catalog, scorer, prompt, "
        "dataset hashes; provenance header scorer/dataset/tools; one config hash per file; legacy and sym files from the same raw bytes).",
        "",
    ]
    lines += md_table(
        ["kind", "key", "file", "rows", "cases / split", "error rows", "sym file", "status"],
        inp.inventory,
    )
    lines += md_table(
        ["file", "config hash", "catalog", "legacy scorer", "sym scorer", "prompt", "check"],
        inp.audit,
    )
    out["inventory"] = inp.inventory
    return lines, out


def _sens_row(i: str, label: str, r: dict[str, Any]) -> list[Any]:
    if "missing" in r:
        return [i, label, "-", "-", "NOT RUN"]
    from final_primary import _verdict

    return [i, label, r["n_cases"], fmt(r["delta_ci"]), _verdict(r)]


def _sens_js(i: str, label: str, r: dict[str, Any]) -> dict[str, Any]:
    if "missing" in r:
        return {"id": i, "variant": label, "missing": r["missing"]}
    return {"id": i, "variant": label, "n_cases": r["n_cases"], "delta": ci_json(r["delta_ci"])}


# ------------------------------------------------------------------ secondary


def secondary(inp: Inputs) -> tuple[list[str], dict[str, Any]]:
    routing = {k: ld.rows for k, ld in inp.routing.items()}
    e2e_sym = {k: ld.sym_rows for k, ld in inp.e2e.items() if ld.sym_rows is not None}
    out: dict[str, Any] = {"smoke": inp.smoke}
    lines = banner(inp) + [
        f"# Part B secondary analyses [C]: families S-e2e and S-routing on `{inp.split}`",
        "",
        "Same machinery as primary.md; Holm within each family (a not-run hypothesis enters with p = 1; S5 and S6 are dropped: their "
        "reference arm is local and no local model runs in phase 2).",
        "",
    ]
    # S-e2e
    scores = primary_scores(routing, e2e_sym)
    same: set[str] = set()
    if {"E9", "E0"} <= e2e_sym.keys():
        same = same_calls_cases(e2e_sym["E9"], e2e_sym["E0"])
        scores["E9@e2e#same"] = keyed(e2e_sym["E9"], "e2e_success", lambda c: c in same)
        scores["E0@e2e#same"] = keyed(e2e_sym["E0"], "e2e_success", lambda c: c in same)
    s2_estimation = 0 < len(same) < S2_MIN_N
    res = evaluate_family(scores, S_E2E, {"S2"} if s2_estimation else set())
    table, js = ctable(res, [i for i, _ in S_E2E], {"S2"} if s2_estimation else set())
    if s2_estimation:
        table[1][-1] = f"estimation only (n = {len(same)} < {S2_MIN_N}, OQ-2); 90% CI: " + (
            fmt([res[1]["verdict"][x] for x in ("delta", "lo", "hi")])
            if "verdict" in res[1]
            else "-"
        )
    lines += [
        "## Family S-e2e (Holm within) [C]",
        "",
        "- **S1:** e2e_success_sym(E9-L-fullskill) − e2e_success_sym(E9-L) > 0, one-sided (confirms D-002 on a fresh split).",
        f"- **S2:** e2e_success_sym(E9-L) − e2e_success_sym(E0-L) on the cases where both arms executed the same sequence of business "
        f"calls; equivalence ±3 pp (TOST, 90% CI inside). Same-calls cases: **{len(same)}**.",
        "",
    ] + md_table(HDR, table)
    out["S-e2e"] = js
    out["S2_same_calls_n"] = len(same)

    # S-routing
    lines += ["## Family S-routing (Holm within) [C]", ""]
    s3 = []
    dev = DEV_FIXED_L.get("E1")
    if inp.split != "test_l":
        s3 = [
            [
                "E1 regex",
                "-",
                "-",
                "-",
                f"not applicable on `{inp.split}` (S3 compares test-L with the fixed dev-L value)",
            ]
        ]
    elif "E1" not in routing:
        s3 = [["E1 regex", "-", "-", "-", "**NOT RUN** (E1 missing)"]]
    else:
        ci = bootstrap_mean(by_case(routing["E1"], lambda r: itt(r, "joint_correct")))
        dv = frozen(dev, "DEV_FIXED_L['E1']")
        assert ci is not None
        gap = (ci[0] - dv, ci[1] - dv, ci[2] - dv)
        verdict = (
            "gap < 0 (test CI entirely below dev)"
            if gap[2] < 0
            else ("gap > 0" if gap[1] > 0 else "CI includes 0")
        )
        s3 = [["E1 regex", f"{100 * dv:.1f}", fmt(ci), fmt(gap), verdict]]
        out["S3"] = {"dev_fixed": dv, "test": ci_json(ci), "gap": ci_json(gap), "verdict": verdict}
    lines += [
        "### S3: regex test-L − dev-L CV joint < 0 (magnitude with a CI; dev fixed; CI rule, no p-value)",
        "",
    ]
    lines += md_table(
        ["router", "dev-L joint %", "test joint % [95% CI]", "gap pp [95% CI]", "verdict"], s3
    )
    res = evaluate_family(primary_scores(routing, {}), S_ROUTING, S_DROPPED)
    table, js = ctable(res, [i for i, _ in S_ROUTING], S_DROPPED)
    lines += [
        "### S4-S7",
        "",
        "- **S4:** Joint(E3 embedding, Bedrock Titan v2) − Joint(E1 regex), two-sided.",
        "- **S5 (dropped):** Joint(E3c Cohere) − Joint(E3 LOCAL): no local arm on test-L.",
        "- **S6 (dropped):** Joint(E6n Nemotron) − Joint(E6b Qwen3-8B LOCAL) > −3 pp: no local arm on test-L.",
        f"- **S7:** Joint({S7_PROBE}, best pre-declared probe) − Joint(E4 Jev), two-sided.",
        "",
    ] + md_table(HDR, table)
    out["S-routing"] = js
    return lines, out


# ------------------------------------------------------------------ estimation


def _cfg_yaml_l(config: str) -> dict[str, Any]:
    for d in (EXP_L, EXP_S):
        p = d / f"{config}.yaml"
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


def _patch_config_dirs() -> None:
    """final_estimation resolves configs in config/experiments only; the L configs live in
    config/experiments_l (read-only patch of two module attributes, phase-1 code untouched)."""
    import final_estimation

    from routing_study.eval.rescore import config_models

    final_estimation._cfg_yaml = _cfg_yaml_l  # type: ignore[attr-defined]
    final_estimation.config_models = lambda c: config_models(
        c, EXP_L if (EXP_L / f"{c}.yaml").exists() else EXP_S
    )  # type: ignore[attr-defined]


COST_REGIMES = [
    "- **observed**: `cost_usd.routing` as recorded per row (the regime of the H1-L co-primary): every consulted stage's recorded cost;",
    "- **list uncached**: recorded tokens × list price (`config/prices.yaml`), no prompt-cache discount; Jev has no list price, its reported "
    "OpenRouter cost is used; CPU-only routers = 0;",
    "- **modelled cache**: Poisson arrivals at the given QPS, 5-minute TTL refreshed on hit, per prompt prefix (phase-1 model). Model, not measurement.",
]


def cascade_coverage(inp: Inputs) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    md, regex_md = [], []
    for k in ("E7", "E9", "E12"):
        ld = inp.routing.get(k)
        if ld is None:
            md.append([k, "-", "-", "-", "-", "**NOT RUN**"])
            continue
        rs = ld.rows
        js[k] = {}
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
                js[k][f"{lv}|{st}"] = {
                    "n": len(vals),
                    "share": len(vals) / len(rs),
                    "acc": mean(ok) if ok else None,
                }
                md.append(
                    [
                        f"{k} ({ld.name})",
                        lv,
                        st,
                        len(vals),
                        f"{100 * len(vals) / len(rs):.1f}",
                        fnum(mean(ok)) if ok else "-",
                    ]
                )
        cfg = _cfg_yaml_l(rs[0]["config"])
        th = next(
            (
                p.get("min_confidence")
                for p in (((cfg.get("routing") or {}).get("skill") or {}).get("pipeline") or [])
                if p.get("strategy") == "regex"
            ),
            None,
        )
        rx = js[k].get("skill|regex")
        regex_md.append(
            [
                k,
                rs[0]["config"],
                "-" if th is None else f"{th:g}",
                "0.0" if rx is None else f"{100 * rx['share']:.1f}",
                "-" if rx is None or rx["acc"] is None else fnum(rx["acc"]),
            ]
        )
        js[k]["regex_threshold"] = th
    lines = [
        "## E. Cascade coverage per step [E]",
        "",
        "### Regex coverage at its frozen threshold (skill stage)",
        "",
    ]
    lines += md_table(
        [
            "cascade",
            "config",
            "regex min_confidence",
            "share resolved by regex %",
            "skill accuracy there %",
        ],
        regex_md,
    )
    lines += [
        "### Every step (share of rows resolved at each step and accuracy there; tool accuracy given a correct skill)",
        "",
    ]
    lines += md_table(["run", "stage", "resolved by", "rows", "share %", "accuracy %"], md)
    return lines, js


def latency_section(lat: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    md = []
    for s in LAT_L:
        if s not in lat:
            md.append([s, "**NOT RUN**", "", "", "", "", ""])
            continue
        x = lat[s]
        cold = x["cold_ms"]
        md.append(
            [
                s,
                ",".join(map(str, x["blocks"])),
                x["n_warm"],
                fms(_ci3(x["warm"]["50"])),
                fms(_ci3(x["warm"]["95"])),
                f"{np.median(cold):.0f} / {max(cold):.0f}" if cold else "-",
                x["errors"],
            ]
        )
    lines = [
        "## D. Latency p50/p95 [E] (dedicated benchmark only: lat-l-<strategy>-b1..4)",
        "",
        "Warm = every case but the first of each block, error-free; the first case of a block is cold and reported apart. 95% CI: cluster bootstrap over cases.",
        "",
    ]
    return lines + md_table(
        [
            "strategy",
            "blocks",
            "warm n",
            "p50 ms [95% CI]",
            "p95 ms [95% CI]",
            "cold median / max ms",
            "error rows",
        ],
        md,
    ), {s: {k: v for k, v in x.items() if k != "warm_by_case"} for s, x in lat.items()}


E2E_SCORES = (
    ("skill_correct", "skill"),
    ("e2e_success", "e2e_success"),
    ("first_call_success", "= first call"),
    ("clarification_credited", "+ clarification"),
    ("recovered_credited", "+ recovered"),
    ("e2e_strict", "e2e_strict"),
    ("args_valid", "args valid"),
    ("args_invented", "args_invented (lower = better)"),
    ("entity_grounded", "entity_grounded"),
)


def e2e_section(inp: Inputs) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {}
    md, cost_md = [], []
    reg = {r.key: r for r in E2E_L}
    for r in E2E_L:
        ld = inp.e2e.get(r.key)
        if ld is None:
            md.append([r.label, "-", "**NOT RUN**"] + [""] * (len(E2E_SCORES) + 1))
            continue
        for sc_name, rs in (("sym (primary)", ld.sym_rows), ("legacy (sensitivity)", ld.rows)):
            if rs is None:
                md.append([r.label, sc_name, "sym file missing"] + [""] * (len(E2E_SCORES) + 1))
                continue
            row = [r.label, sc_name, len(rs), sum(1 for x in rs if x.get("error"))]
            jj = js.setdefault(r.key, {"run": ld.name, "label": reg[r.key].label}).setdefault(
                sc_name.split()[0], {}
            )
            for s, _ in E2E_SCORES:
                ci = bootstrap_mean(by_case(rs, lambda x, s=s: itt(x, s)))
                jj[s] = ci_json(ci)
                row.append(fmt(ci))
            md.append(row)
        rs = ld.rows
        tot, rt, ag = per1k(rs, "total"), per1k(rs, "routing"), per1k(rs, "agent")
        lst = bootstrap_mean(by_case(rs, lambda x: row_list_uncached(x)[0]))
        ptok = bootstrap_mean(by_case(rs, lambda x: (x.get("tokens") or {}).get("prompt")))
        js[r.key]["cost_turn_1k"] = ci_json(tot)
        js[r.key]["cost_list_1k"] = ci_json(None if lst is None else [1000 * v for v in lst])
        cost_md.append(
            [
                r.label,
                fmt(tot, 1, 2),
                fmt(rt, 1, 2),
                fmt(ag, 1, 2),
                fmt(lst, 1000, 2),
                fmt(ptok, 1, 0),
            ]
        )
    var_md = []
    for k, ld in sorted(inp.variance.items()):
        main = inp.e2e.get(k)
        if main is None or ld.sym_rows is None or main.sym_rows is None:
            var_md.append([k, ld.name, "main run or sym file missing", "", ""])
            continue
        m = {x["case_id"]: x for x in main.sym_rows}
        shared = [x for x in ld.sym_rows if x["case_id"] in m]
        flips = {
            x["case_id"]: [
                float((itt(x, "e2e_success") or 0) != (itt(m[x["case_id"]], "e2e_success") or 0))
            ]
            for x in shared
        }
        ci = bootstrap_mean(flips)
        js.setdefault("executor_variance", {})[k] = {"n": len(shared), "flip": ci_json(ci)}
        var_md.append(
            [
                k,
                ld.name,
                len(shared),
                fmt(ci),
                f"{100 * mean(itt(m[x['case_id']], 'e2e_success') or 0 for x in shared):.1f} -> {100 * mean(itt(x, 'e2e_success') or 0 for x in shared):.1f}",
            ]
        )
    lines = [
        "## F. End-to-end decomposition (executor Sonnet 5; ITT, % [95% CI]) [E]",
        "",
        "e2e_success = first call + clarification + recovered (disjoint). Both scorers; the symmetric one is the primary.",
        "",
    ]
    lines += md_table(["run", "scorer", "rows", "errors"] + [lab for _, lab in E2E_SCORES], md)
    lines += [
        "### Cost per turn (US$ per 1 000 turns, observed; list = no prompt-cache discount)",
        "",
    ]
    lines += md_table(
        [
            "run",
            "total [CI]",
            "routing [CI]",
            "executor [CI]",
            "list uncached total [CI]",
            "executor prompt tokens/turn [CI]",
        ],
        cost_md,
    )
    lines += ["### Executor variance (rep 2 on 60 cases; symmetric scorer)", ""]
    lines += md_table(
        ["arm", "run", "cases", "e2e flip % [CI]", "main -> rep2 %"],
        var_md or [["-", "**NOT RUN**", "", "", ""]],
    )
    return lines, js


def flips_section(inp: Inputs) -> tuple[list[str], dict[str, Any]]:
    from final_estimation import _flip

    js: dict[str, Any] = {}
    md = []
    for k, (name, label) in REPEATS_L.items():
        ld = inp.repeat.get(k)
        if ld is None:
            md.append([label, name, "**NOT RUN**", "", ""])
            continue
        f = _flip([r for r in ld.rows if r["rep"] == 1], [r for r in ld.rows if r["rep"] == 2])
        js[k] = f
        md.append(
            [
                label,
                ld.name,
                f["n"],
                f"{f['decision_flips']} ({fmt(_ci3(f['decision_flip']))})",
                f"{f['joint_flips']} ({fmt(_ci3(f['joint_flip']))})",
            ]
        )
    lines = ["## G. Rep-flip rates (rep 1 vs rep 2, temperature 0) [E]", ""]
    return lines + md_table(
        ["arm", "run", "cases", "decision flips n (% [CI])", "joint flips n (% [CI])"], md
    ), js


def _groups() -> list[tuple[str, frozenset[str]]]:
    import generate_l

    out = [(f"G{i}", frozenset(ts)) for i, (_, ts) in enumerate(generate_l.AMBIG_GROUPS_G, start=1)]
    return out + [("P1", frozenset(ts)) for _, ts in generate_l.AMBIG_GROUPS_P1]


def orig_case(case: dict[str, Any]) -> bool:
    """X2 orig subset: every acceptable tool is one of the 18 phase-1 tools, or out of scope."""
    from common_l import ORIG_TOOLS

    orig = set(ORIG_TOOLS) | {"__abstain__"}
    return case["category"] == "fora_escopo" or all(
        t in orig for t in case["expected"]["acceptable_tools"]
    )


def breakdowns(inp: Inputs) -> tuple[list[str], dict[str, Any]]:
    groups = _groups()

    def group_of(c: dict[str, Any]) -> str | None:
        if c["category"] != "ambiguo":
            return None
        s = frozenset(c["expected"]["acceptable_tools"])
        return next((g for g, ts in groups if ts == s), "other")

    gid = {cid: group_of(c) for cid, c in inp.cases.items()}
    sub = {cid: "orig 18 tools" if orig_case(c) else "new tools" for cid, c in inp.cases.items()}
    skill = {cid: c["expected"]["acceptable_skills"][0] for cid, c in inp.cases.items()}
    gnames = [g for g, _ in groups[:12]] + ["P1", "other"]
    skills = sorted(set(skill.values()))
    js: dict[str, Any] = {}

    def acc(rs: list[dict[str, Any]], keep: Callable[[str], bool]) -> str:
        vals = by_case([r for r in rs if keep(r["case_id"])], lambda r: itt(r, "joint_correct"))
        return "-" if not vals else f"{100 * mean(mean(v) for v in vals.values()):.1f}"

    cat_md, sub_md, sk_md, g_md = [], [], [], []
    for k, ld in inp.routing.items():
        rs = ld.rows
        cat_md.append(
            [k] + [acc(rs, lambda c, x=x: inp.cases[c]["category"] == x) for x in CATEGORIES]
        )
        sub_md.append(
            [k] + [acc(rs, lambda c, x=x: sub[c] == x) for x in ("orig 18 tools", "new tools")]
        )
        sk_md.append([k] + [acc(rs, lambda c, x=x: skill[c] == x) for x in skills])
        g_md.append([k] + [acc(rs, lambda c, x=x: gid[c] == x) for x in gnames])
        js[k] = {
            "category": dict(zip(CATEGORIES, cat_md[-1][1:], strict=True)),
            "subset": dict(zip(("orig", "new"), sub_md[-1][1:], strict=True)),
        }
    n_cat = Counter(c["category"] for c in inp.cases.values())
    n_sub = Counter(sub.values())
    n_sk = Counter(skill.values())
    n_g = Counter(g for g in gid.values() if g)
    lines = [
        "## I. Breakdowns (joint %, ITT, point estimates; per-cell n in the header) [E]",
        "",
        "### Per category",
        "",
    ]
    lines += md_table(["arm"] + [f"{x} (n={n_cat[x]})" for x in CATEGORIES], cat_md)
    lines += [
        "### Original vs new tools (orig = every acceptable tool among the 18 phase-1 tools, or out of scope)",
        "",
    ]
    lines += md_table(
        ["arm"] + [f"{x} (n={n_sub[x]})" for x in ("orig 18 tools", "new tools")], sub_md
    )
    lines += ["### Per skill (first acceptable skill)", ""]
    lines += md_table(["arm"] + [f"{x} (n={n_sk[x]})" for x in skills], sk_md)
    lines += [
        "### Per confusable group (ambiguo cases; G1-G12 large-profile groups, P1 = phase-1 groups)",
        "",
    ]
    lines += md_table(["arm"] + [f"{x} (n={n_g[x]})" for x in gnames], g_md)
    return lines, js


def estimation(inp: Inputs, lat: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    from addendum_a import _retitle, errors_parse
    from final_estimation import calibration_table, strategy_table

    _patch_config_dirs()
    ctx = context(inp)
    est: dict[str, Any] = {"smoke": inp.smoke, "split": inp.split}
    lines = banner(inp) + [
        f"# Part B estimation tables [E] (prereg-v2 §3 'Estimation only'; CIs, no tests) on `{inp.split}`",
        "",
        "Generated by `scripts/analysis/phase2_b.py`. ITT; 95% CIs = cluster bootstrap over case ids (10k, seed 20260930).",
        "",
    ]
    if ctx.routing:
        md, js = strategy_table(ctx, prefix_sizes([r for rs in ctx.routing.values() for r in rs]))
        md = _retitle(md, "## A. Per strategy", "## A. Per strategy [E]")
        i = next(n for n, ln in enumerate(md) if ln.startswith("- **observed**"))
        j = next(n for n in range(i, len(md)) if md[n] == "")
        lines += md[:i] + COST_REGIMES + md[j:]
        est["strategies"] = js
        md, js = calibration_table(ctx)
        md = [
            ln.replace("test-v2", inp.split)
            for ln in _retitle(
                _retitle(md, "## B. Calibration", "## B. Calibration [E]"),
                "## C. Selective prediction",
                "## C. Selective prediction [E]",
            )
        ]
        lines += md
        est["calibration"] = js
    else:
        lines += ["## A-C. Per strategy, cost, calibration: **NOT RUN** (no routing arm)", ""]
        est["strategies"] = {}
    md, est["latency"] = latency_section(lat)
    lines += md
    md, est["cascades"] = cascade_coverage(inp)
    lines += md
    md, est["e2e"] = e2e_section(inp)
    lines += md
    md, est["flips"] = flips_section(inp)
    lines += md
    if ctx.routing:
        md, est["errors"] = errors_parse(ctx)
        lines += _retitle(
            md, "## E. Error and parse-failure rates", "## H. Error and parse-failure rates [E]"
        )
        md, est["breakdowns"] = breakdowns(inp)
        lines += md
    return lines, est


# ------------------------------------------------------------------ catalog size (X1-X4)


def catalog_size(inp: Inputs) -> tuple[list[str], dict[str, Any]]:
    js: dict[str, Any] = {"smoke": inp.smoke, "x1_routing": {}, "x1_e2e": {}, "x2": {}}
    lines = banner(inp) + [
        f"# Catalog size, 18 vs 62 tools [X] (EXPLORATORY) on `{inp.split}`",
        "",
        "Generated by `scripts/analysis/phase2_b.py`. Joint = joint top-1 (legacy routing scorer); e2e = `e2e_success_sym` (both phases "
        "re-scored with the same symmetric scorer) with the legacy one beside it.",
        "",
        "## X1. Cross-dataset, unpaired [X]",
        "",
        CAVEAT_X,
        "",
        "Independent cluster bootstraps per split (10k each; seeds 20260930 and 20260931); Δ = L − test-v2.",
        "",
    ]
    md = []
    for k, ld in inp.routing.items():
        v2 = inp.x1_routing.get(k)
        a = by_case(ld.rows, lambda r: itt(r, "joint_correct"))
        if v2 is None:
            md.append(
                [
                    k,
                    "-",
                    fmt(bootstrap_mean(a)),
                    "-",
                    "no test-v2 counterpart" if k not in X1_ROUTING else "test-v2 file missing",
                ]
            )
            continue
        b = by_case(v2.rows, lambda r: itt(r, "joint_correct"))
        d = indep_delta(a, b)
        js["x1_routing"][k] = {
            "l": ci_json(bootstrap_mean(a)),
            "v2": ci_json(bootstrap_mean(b)),
            "delta": ci_json(d),
            "v2_run": v2.name,
            "n_l": len(a),
            "n_v2": len(b),
        }
        md.append(
            [
                k,
                f"{v2.name} (n={len(b)})",
                f"{fmt(bootstrap_mean(a))} (n={len(a)})",
                fmt(bootstrap_mean(b)),
                fmt(d),
            ]
        )
    lines += ["### Routing joint", "", CAVEAT_X, ""]
    lines += md_table(
        [
            "strategy",
            "test-v2 run",
            "joint % L [CI]",
            "joint % test-v2 [CI]",
            "Δ L − test-v2 pp [CI] (unpaired)",
        ],
        md or [["-", "", "", "", "no routing arm"]],
    )
    md = []
    for k, ld in inp.e2e.items():
        v2 = inp.x1_e2e.get(k)
        for sc, la, lb in (
            ("sym", ld.sym_rows, v2.sym_rows if v2 else None),
            ("legacy", ld.rows, v2.rows if v2 else None),
        ):
            if la is None or lb is None:
                md.append([k, sc, "-", "-", "missing file (L or test-v2)"])
                continue
            a = by_case(la, lambda r: itt(r, "e2e_success"))
            b = by_case(lb, lambda r: itt(r, "e2e_success"))
            d = indep_delta(a, b)
            js["x1_e2e"][f"{k}|{sc}"] = {
                "l": ci_json(bootstrap_mean(a)),
                "v2": ci_json(bootstrap_mean(b)),
                "delta": ci_json(d),
            }
            md.append([k, sc, fmt(bootstrap_mean(a)), fmt(bootstrap_mean(b)), fmt(d)])
    lines += ["### e2e success", "", CAVEAT_X, ""]
    lines += md_table(
        ["arm", "scorer", "e2e % L [CI]", "e2e % test-v2 [CI]", "Δ pp [CI] (unpaired)"],
        md or [["-", "", "", "", "no e2e arm"]],
    )

    # X2
    orig = {c for c, x in inp.cases.items() if orig_case(x)}
    lines += [
        "## X2. Paired catalog-size subset [X] (secondary estimation)",
        "",
        CAVEAT_X2,
        "",
        f"Orig subset of `{inp.split}`: **{len(orig)}** of {len(inp.cases)} cases (every acceptable tool among the 18 phase-1 tools, or out of scope). "
        "Small-profile run = `l-x2-small-<key>-routing-r1` (catalog 128584617807) on these cases; large = the main arm restricted to them. "
        "Paired cluster bootstrap over the shared cases.",
        "",
    ]
    md = []
    for k in X2_KEYS:
        lg, sm = inp.routing.get(k), inp.x2.get(k)
        lg_ci = (
            bootstrap_mean(
                by_case(
                    [r for r in lg.rows if r["case_id"] in orig], lambda r: itt(r, "joint_correct")
                )
            )
            if lg
            else None
        )
        if lg is None or sm is None:
            md.append(
                [
                    k,
                    fmt(lg_ci),
                    "-",
                    "-",
                    "-",
                    "**NOT RUN** ("
                    + ("small-profile run missing" if sm is None else "large arm missing")
                    + ")",
                ]
            )
            continue
        a = keyed(lg.rows, "joint_correct", lambda c: c in orig)
        b = keyed(sm.rows, "joint_correct", lambda c: c in orig)
        d = paired_delta(a, b)
        sm_ci = bootstrap_mean(
            by_case([r for r in sm.rows if r["case_id"] in orig], lambda r: itt(r, "joint_correct"))
        )
        n = len({c for c, _ in a} & {c for c, _ in b})  # type: ignore[misc]
        js["x2"][k] = {
            "large": ci_json(lg_ci),
            "small": ci_json(sm_ci),
            "delta": ci_json(d),
            "n": n,
        }
        md.append(
            [
                k,
                fmt(lg_ci),
                fmt(sm_ci),
                n,
                fmt(d),
                "Δ < 0: 62 tools cost accuracy"
                if d and d[2] < 0
                else ("Δ > 0" if d and d[1] > 0 else "CI includes 0"),
            ]
        )
    lines += md_table(
        [
            "strategy",
            "62-tool joint % on orig [CI]",
            "18-tool joint % on orig [CI]",
            "paired cases",
            "Δ 62 − 18 pp [CI]",
            "reading",
        ],
        md,
    )
    sub_md = []
    for k, ld in inp.routing.items():
        o = bootstrap_mean(
            by_case([r for r in ld.rows if r["case_id"] in orig], lambda r: itt(r, "joint_correct"))
        )
        nw = bootstrap_mean(
            by_case(
                [r for r in ld.rows if r["case_id"] not in orig], lambda r: itt(r, "joint_correct")
            )
        )
        sub_md.append([k, fmt(o), fmt(nw)])
    lines += [
        "### Large-profile joint on the orig subset vs the new-tool cases (descriptive; different cases)",
        "",
    ]
    lines += md_table(
        ["strategy", "orig subset % [CI]", "new-tool cases % [CI]"], sub_md or [["-", "", ""]]
    )

    # X3
    lines += ["## X3. Haiku 4.5 prompt cache with the larger prompt [X]", ""]
    hk = inp.routing.get("E6")
    if hk is None:
        lines += ["**NOT RUN** (E6 Haiku missing).", ""]
    else:
        steps = [
            st
            for r in hk.rows
            for lv in ("skill", "tool")
            for st in (r.get(lv) or {}).get("steps") or []
            if (st.get("usage") or {}).get("provider") == "bedrock"
        ]
        u = [st["usage"] for st in steps]
        pt = [int(x.get("prompt_tokens") or 0) for x in u]
        x3 = {
            "calls": len(u),
            "mean_prompt_tokens": mean(pt) if pt else None,
            "share_prompt_ge_4096": mean(p >= 4096 for p in pt) if pt else None,
            "share_cache_read": mean(int(x.get("cache_read") or 0) > 0 for x in u) if u else None,
            "share_cache_write": mean(int(x.get("cache_write") or 0) > 0 for x in u) if u else None,
            "observed_1k": ci_json(per1k(hk.rows, "routing")),
            "list_uncached_1k": ci_json(
                (lambda c: None if c is None else [1000 * v for v in c])(
                    bootstrap_mean(by_case(hk.rows, lambda r: row_list_uncached(r)[0]))
                )
            ),
        }
        js["x3"] = x3
        lines += md_table(
            [
                "stage calls",
                "mean prompt tokens",
                "calls ≥ 4 096 tokens %",
                "calls with cache read %",
                "calls with cache write %",
                "observed US$/1k [CI]",
                "list uncached US$/1k [CI]",
            ],
            [
                [
                    x3["calls"],
                    fnum(x3["mean_prompt_tokens"], 1, 0),
                    fnum(x3["share_prompt_ge_4096"]),
                    fnum(x3["share_cache_read"]),
                    fnum(x3["share_cache_write"]),
                    fmt(_ci3(x3["observed_1k"]), 1, 3),
                    fmt(_ci3(x3["list_uncached_1k"]), 1, 3),
                ]
            ],
        )
    lines += [
        "## X4. Phase-1 symmetric re-score [X]",
        "",
        "Already run before the freeze and reported as exploratory in `docs/results/phase1-sym/exploratory_e2e_sym.md` (never re-labelled).",
        "",
    ]
    return lines, js


# ------------------------------------------------------------------ figures


FAM_COLOR = {
    "lexical": "#2a78d6",
    "managed-semantic": "#1baf7a",
    "api-llm": "#eb6834",
    "cascade": "#4a3aa7",
    "native": "#52514e",
}


def figure_data(inp: Inputs, est: dict[str, Any], cat: dict[str, Any]) -> dict[str, Any]:
    pts = []
    for k, s in (est.get("strategies") or {}).items():
        p95 = (est["latency"].get(s.get("lat") or "") or {}).get("warm", {}).get("95")
        pts.append(
            {
                "key": k,
                "family": s["family"],
                "joint": s["joint"],
                "cost_1k": {
                    x: 1000 * v
                    for x, v in (
                        s["cost_observed_per_case"] or {"point": 0, "lo": 0, "hi": 0}
                    ).items()
                },
                "p95": p95,
            }
        )
    e2e = []
    for k, d in (est.get("e2e") or {}).items():
        if k == "executor_variance":
            continue
        for sc in ("sym", "legacy"):
            if sc in d:
                e2e.append(
                    {
                        "arm": k,
                        "scorer": sc,
                        **{
                            s: (d[sc].get(s) or {}).get("point")
                            for s in (
                                "first_call_success",
                                "clarification_credited",
                                "recovered_credited",
                                "e2e_success",
                            )
                        },
                    }
                )
    return {
        "smoke": inp.smoke,
        "split": inp.split,
        "points": pts,
        "e2e": e2e,
        "x1": cat["x1_routing"],
        "x1_e2e": cat["x1_e2e"],
        "x2": cat["x2"],
    }


def run_figures(fd: dict[str, Any], fig_dir: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import final_figures  # noqa: F401  (rcParams: shared light surface)
    import matplotlib.pyplot as plt
    from final_figures import _labels

    fig_dir.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    tag = f" — SMOKE ({fd['split']}), NOT A RESULT" if fd["smoke"] else ""

    def save(fig: Any, name: str) -> None:
        p = fig_dir / name
        fig.savefig(p, dpi=200, bbox_inches="tight")
        plt.close(fig)
        out.append(str(p))

    def err(ci: dict[str, float], scale: float = 100.0) -> list[list[float]]:
        return [[scale * (ci["point"] - ci["lo"])], [scale * (ci["hi"] - ci["point"])]]

    pts = fd["points"]
    # 1. accuracy x cost
    if pts:
        fig, ax = plt.subplots(figsize=(9, 5.6))
        lab = []
        for p in pts:
            c = p["cost_1k"]
            x = max(c["point"], 1e-4)
            ax.errorbar(
                x,
                100 * p["joint"]["point"],
                yerr=err(p["joint"]),
                xerr=None if c["point"] <= 0 else [[x - c["lo"]], [c["hi"] - x]],
                fmt="o",
                color=FAM_COLOR.get(p["family"], "#52514e"),
                ms=7,
            )
            lab.append((x, 100 * p["joint"]["point"], p["key"]))
        ax.set_xscale("log")
        _labels(ax, lab)
        ax.set_xlabel(
            "routing cost, US$ per 1 000 cases (observed regime, log; US$ 0 drawn at 1e-4)"
        )
        ax.set_ylabel(f"joint accuracy % on {fd['split']} (ITT, 95% CI)")
        ax.set_title("Accuracy vs cost, 62-tool catalog" + tag)
        save(fig, "final-b-accuracy-cost.png")
    # 2. accuracy x p95
    lp = [p for p in pts if p.get("p95")]
    if lp:
        fig, ax = plt.subplots(figsize=(9, 5.6))
        lab = []
        for p in lp:
            q = p["p95"]
            x = max(q["point"], 0.05)
            ax.errorbar(
                x,
                100 * p["joint"]["point"],
                yerr=err(p["joint"]),
                xerr=[[max(x - q["lo"], 0)], [max(q["hi"] - x, 0)]],
                fmt="o",
                color=FAM_COLOR.get(p["family"], "#52514e"),
                ms=7,
            )
            lab.append((x, 100 * p["joint"]["point"], p["key"]))
        ax.set_xscale("log")
        _labels(ax, lab)
        ax.set_xlabel("warm p95 routing latency, ms (log; 95% CI; dedicated benchmark)")
        ax.set_ylabel(f"joint accuracy % on {fd['split']} (ITT, 95% CI)")
        ax.set_title("Accuracy vs p95 latency, 62-tool catalog" + tag)
        save(fig, "final-b-accuracy-latency-p95.png")
    # 3. e2e decomposition
    if fd["e2e"]:
        fig, ax = plt.subplots(figsize=(8, 4.8))
        names = [f"{e['arm']}\n{e['scorer']}" for e in fd["e2e"]]
        bottom = np.zeros(len(names))
        for s, col, lab in (
            ("first_call_success", "#2a78d6", "first call"),
            ("clarification_credited", "#eda100", "clarification"),
            ("recovered_credited", "#1baf7a", "recovered"),
        ):
            v = np.array([100 * (e[s] or 0) for e in fd["e2e"]])
            ax.bar(names, v, bottom=bottom, color=col, label=lab, width=0.6)
            bottom += v
        for i, e in enumerate(fd["e2e"]):
            ax.text(
                i, bottom[i] + 0.8, f"{100 * (e['e2e_success'] or 0):.1f}", ha="center", fontsize=8
            )
        ax.set_ylabel("e2e success % (ITT)")
        ax.set_title("e2e decomposition, symmetric (primary) vs legacy scorer" + tag)
        ax.legend(loc="upper right", fontsize=8)
        save(fig, "final-b-e2e-decomposition.png")
    # 4. 18 vs 62
    x1, x2 = fd["x1"], fd["x2"]
    if x1 or x2 or fd["x1_e2e"]:
        fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), gridspec_kw={"width_ratios": [3, 2]})
        ax = axes[0]
        rows = [(k, v["v2"], v["l"]) for k, v in x1.items()] + [
            (f"{k.split('|')[0]} e2e", v["v2"], v["l"])
            for k, v in fd["x1_e2e"].items()
            if k.endswith("|sym")
        ]
        for i, (_k, a, b) in enumerate(rows):
            ax.plot(
                [100 * a["point"], 100 * b["point"]],
                [i + 0.12, i - 0.12],
                color="#b5b3ad",
                lw=1.2,
                zorder=1,
            )
            ax.errorbar(
                100 * a["point"],
                i + 0.12,
                xerr=err(a),
                fmt="o",
                color="#2a78d6",
                ms=6,
                label="18 tools (test-v2)" if i == 0 else None,
            )
            ax.errorbar(
                100 * b["point"],
                i - 0.12,
                xerr=err(b),
                fmt="D",
                color="#eb6834",
                ms=6,
                label=f"62 tools ({fd['split']})" if i == 0 else None,
            )
        ax.set_yticks(range(len(rows)), [r[0] for r in rows])
        ax.set_xlabel("joint % (routing) / e2e_success_sym % (e2e), 95% CI")
        ax.set_title("X1: different datasets (unpaired)")
        ax.legend(fontsize=8, loc="lower left")
        ax = axes[1]
        ks = list(x2)
        for i, k in enumerate(ks):
            d = x2[k]["delta"]
            ax.errorbar(100 * d["point"], i, xerr=err(d), fmt="s", color="#4a3aa7", ms=6)
        ax.axvline(0, color="#52514e", lw=0.8, ls=":")
        ax.set_yticks(range(len(ks)), ks)
        ax.set_xlabel("Δ joint 62 − 18 tools, pp (paired, orig subset)")
        ax.set_title("X2: same cases" if ks else "X2: not run")
        if not ks:
            ax.text(
                0.5,
                0.5,
                "no small-profile run on the orig subset",
                transform=ax.transAxes,
                ha="center",
                fontsize=9,
            )
        fig.suptitle(
            "Catalog size 18 vs 62 tools"
            + tag
            + "\nCaveat: datasets, label sets and catalog text differ; routers re-tuned per catalog (system vs system, not a pure size effect).",
            fontsize=9,
        )
        save(fig, "final-b-catalog-18-vs-62.png")
    return out


def figures_step(data_path: Path, fig_dir: Path) -> list[str]:
    if importlib.util.find_spec("matplotlib") is not None:
        return run_figures(json.loads(data_path.read_text(encoding="utf-8")), fig_dir)
    res = subprocess.run(
        [
            "uv",
            "run",
            "--with",
            "matplotlib",
            "python",
            str(Path(__file__).resolve()),
            "--figures-only",
            str(data_path),
            str(fig_dir),
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


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--manifest", help="config/study_manifest_l.yaml (registered names, COMPLETE runs only)"
    )
    ap.add_argument(
        "--run",
        action="append",
        help="kind:KEY=name|path[|sym path] (kind: routing e2e variance repeat x2 lat); overrides the manifest",
    )
    ap.add_argument("--split", default="test_l")
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="label every output SMOKE and write under results/phase2l/analysis_smoke/",
    )
    ap.add_argument(
        "--out", help="output directory (default docs/results/phase2-b, or the smoke dir)"
    )
    ap.add_argument("--no-figures", action="store_true")
    ap.add_argument("--figures-only", nargs=2, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.figures_only:
        for p in run_figures(
            json.loads(Path(args.figures_only[0]).read_text(encoding="utf-8")),
            Path(args.figures_only[1]),
        ):
            print(p)
        return
    if not args.smoke and args.split != "test_l":
        raise SystemExit("a non-test_l split is only analysed with --smoke")
    if not args.manifest and not args.run:
        raise SystemExit("give --manifest and/or --run")
    out = Path(args.out) if args.out else (SMOKE_OUT if args.smoke else OUT)
    fig_dir = out / "figures" if args.smoke else FIG
    inp = load_inputs(args)
    lat = {s: lat_summary(rows) for s, rows in inp.lat.items()}
    p_lines, p_js = primary(inp, lat)
    write(out / "primary.md", "\n".join(p_lines))
    write_json(out / "primary.json", p_js)
    s_lines, s_js = secondary(inp)
    write(out / "secondary.md", "\n".join(s_lines))
    write_json(out / "secondary.json", s_js)
    e_lines, e_js = estimation(inp, lat)
    write(out / "estimation.md", "\n".join(e_lines))
    c_lines, c_js = catalog_size(inp)
    write(out / "catalog_size.md", "\n".join(c_lines))
    write_json(out / "catalog_size.json", c_js)
    e_js["figure_data"] = figure_data(inp, e_js, c_js)
    write_json(out / "estimation.json", e_js)
    write_json(out / "figure_data.json", e_js["figure_data"])
    figs = [] if args.no_figures else figures_step(out / "figure_data.json", fig_dir)
    for p in sorted(out.glob("*.*")):
        print(f"  {p}")
    for f in figs:
        print(f"  {f}")


if __name__ == "__main__":
    main()
