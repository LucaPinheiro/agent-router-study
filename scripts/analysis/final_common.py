# ruff: noqa: E501  (report prose and table rows)
"""Shared helpers of the final test-v2 analysis (scripts/analysis/final_*.py).

Read-only over `results/rescored/*.jsonl` (the scorer of record), `results/final/run-manifest.log`
(run status), `config/` (prices, prompt-selection maps, experiment configs) and `docs/results/`
(dev references). Every statistic reuses `routing_study.eval.{stats,metrics,report}`: cluster
bootstrap over case ids, 10k resamples, seed 20260930; per-case means over reps before any
paired test; intention to treat (an error row is wrong). Nothing here writes outside
`results/analysis/`, `docs/results/final/` and `estudos/figuras/`.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache, lru_cache
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
import yaml

from routing_study.eval.report import itt
from routing_study.eval.rescore import read_rescored
from routing_study.eval.stats import BOOT_N, BOOT_SEED, bootstrap_mean

ROOT = Path(__file__).resolve().parents[2]
RESCORED = ROOT / "results" / "rescored"
LOG = ROOT / "results" / "final" / "run-manifest.log"
OUT = ROOT / "results" / "analysis"
DOCS_OUT = ROOT / "docs" / "results" / "final"
FIG = ROOT / "estudos" / "figuras"
PRICES = ROOT / "config" / "prices.yaml"
PROMPT_SELECTION = ROOT / "config" / "prompt_selection.yaml"
PARETO_DEV = ROOT / "docs" / "results" / "cascade-pareto-dev.csv"

# ------------------------------------------------------------------ run registry


@dataclass(frozen=True)
class Run:
    key: str  # short label used in tables / figures
    name: str  # manifest run name (= rescored file stem)
    label: str  # human label
    family: str  # lexical | local-semantic | api-llm | cascade | native
    status: str = "estimation"  # confirmatory | estimation | exploratory
    lat: str | None = None  # lat-<lat>-b* benchmark id, if any
    local: bool = True  # no external API call in the routing path


ROUTING = [
    Run("E1", "v2-e1-regex-routing-r1", "E1 regex", "lexical", lat="regex"),
    Run("E2", "v2-e2-bm25-routing-r1", "E2 BM25", "lexical", lat="bm25"),
    Run(
        "E3",
        "v2-e3-embedding-routing-r1",
        "E3 embedding (qwen3-emb 8B)",
        "local-semantic",
        lat="embedding",
    ),
    Run(
        "E3-0.6B",
        "v2-e3-embedding-qwen06b-routing-r1",
        "E3 ablation qwen3-emb 0.6B",
        "local-semantic",
    ),
    Run("E3-bge", "v2-e3-embedding-bgem3-routing-r1", "E3 ablation bge-m3", "local-semantic"),
    Run(
        "E10",
        "v2-e10-classifier-routing-r1",
        "E10 classifier (probe)",
        "local-semantic",
        lat="classifier",
    ),
    Run(
        "E11",
        "v2-e11-hybrid-routing-r1",
        "E11 hybrid regex+classifier",
        "local-semantic",
        lat="hybrid",
    ),
    Run(
        "E6b",
        "v2-e6b-qwen-canonical-routing-r1",
        "E6b Qwen3-8B local",
        "local-semantic",
        lat="qwen",
    ),
    Run("E4", "v2-e4-jev-canonical-routing-r3", "E4 Jev", "api-llm", lat="jev", local=False),
    Run(
        "E5",
        "v2-e5-sonnet-canonical-routing-r3",
        "E5 Sonnet 5",
        "api-llm",
        "confirmatory",
        lat="sonnet",
        local=False,
    ),
    Run(
        "E6",
        "v2-e6-haiku-canonical-routing-r1",
        "E6 Haiku 4.5",
        "api-llm",
        lat="haiku",
        local=False,
    ),
    Run(
        "E7",
        "v2-e7-tuned-routing-r3",
        "E7 regex->Jev",
        "cascade",
        "confirmatory",
        lat="e7",
        local=False,
    ),
    Run("E8", "v2-e8-tuned-routing-r3", "E8 regex->Sonnet", "cascade", lat="e8", local=False),
    Run(
        "E9",
        "v2-e9-tuned-routing-r3",
        "E9 regex->Jev->Sonnet",
        "cascade",
        "confirmatory",
        lat="e9",
        local=False,
    ),
    Run(
        "E12",
        "x-e12-hybrid-tuned-routing-r3",
        "E12 hybrid->Jev->Sonnet (exploratory)",
        "cascade",
        "exploratory",
        local=False,
    ),
    Run(
        "E4-P6c",
        "x-e4-jev-p6c-routing-r1",
        "E4 Jev P0+P6c (exploratory)",
        "api-llm",
        "exploratory",
        local=False,
    ),
]
E2E = [
    Run(
        "E0", "v2-e0-native-e2e-r1", "E0 native (no router)", "native", "confirmatory", local=False
    ),
    Run("E1", "v2-e1-regex-e2e-r1", "E1 regex", "lexical", local=False),
    Run("E5", "v2-e5-sonnet-canonical-e2e-r1", "E5 Sonnet 5", "api-llm", local=False),
    Run("E6b", "v2-e6b-qwen-canonical-e2e-r1", "E6b Qwen3-8B local", "local-semantic", local=False),
    Run("E7", "v2-e7-tuned-e2e-r1", "E7 regex->Jev", "cascade", local=False),
    Run(
        "E9", "v2-e9-tuned-e2e-r1", "E9 regex->Jev->Sonnet", "cascade", "confirmatory", local=False
    ),
    Run("E11", "v2-e11-hybrid-e2e-r1", "E11 hybrid", "local-semantic", local=False),
]
E2E_VARIANCE = {"E0": "v2-e0-native-e2e-rep2-60", "E9": "v2-e9-tuned-e2e-rep2-60"}
REPEATS = {  # label -> (repeat run, main run whose rep 1 it shares)
    "E1 regex (20 cases x 2)": ("v2-e1-regex-routing-repeat20", "v2-e1-regex-routing-r1"),
    "E6 Haiku 4.5 (60 cases x 2)": (
        "v2-e6-haiku-canonical-rep2-60",
        "v2-e6-haiku-canonical-routing-r1",
    ),
    "E6b Qwen3-8B (50 cases x 2)": (
        "v2-e6b-qwen-canonical-repeat50",
        "v2-e6b-qwen-canonical-routing-r1",
    ),
}
SHADOW = "v2-shadow-tuned-routing-r3"
V1 = {
    "E1": "v1-e1-regex-routing-r1",
    "E2": "v1-e2-bm25-routing-r1",
    "E3": "v1-e3-embedding-routing-r1",
    "E10": "v1-e10-classifier-routing-r1",
    "E11": "v1-e11-hybrid-routing-r1",
}
LAT = [
    "regex",
    "bm25",
    "embedding",
    "classifier",
    "hybrid",
    "qwen",
    "jev",
    "sonnet",
    "haiku",
    "e7",
    "e8",
    "e9",
]
LAT_LOCAL = {"regex", "bm25", "embedding", "classifier", "hybrid", "qwen"}
CATEGORIES = ("direto", "parafrase", "ambiguo", "multiturno", "fora_escopo", "adversarial")

# dev numbers fixed by the pre-registration (S3)
DEV_FIXED = {"E1": 0.848, "E2": 0.557}

# palette (dataviz reference palette, light surface; validated all-pairs for these 4 slots)
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e4e3df"
FAMILY_COLOR = {
    "lexical": "#2a78d6",
    "api-llm": "#eb6834",
    "local-semantic": "#1baf7a",
    "cascade": "#4a3aa7",
    "native": "#52514e",
}
FAMILY_MARKER = {
    "lexical": "s",
    "api-llm": "o",
    "local-semantic": "D",
    "cascade": "^",
    "native": "P",
}


# ------------------------------------------------------------------ status + loading


def run_status() -> dict[str, str]:
    """run name -> last status word in the manifest log (COMPLETE, FLAGGED, RUN, ...)."""
    out: dict[str, str] = {}
    if not LOG.exists():
        return out
    pat = re.compile(r"^\S+ (COMPLETE|FLAGGED|ABORT\w*|REFUSED|SKIP\w*|RUN|RESCORED) ([^:\s]+)")
    for line in LOG.read_text(encoding="utf-8").splitlines():
        m = pat.match(line)
        if m:
            out[m.group(2)] = m.group(1)
    return out


@cache
def _load(name: str) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    path = RESCORED / f"{name}.jsonl"
    if not path.exists():
        return None
    return read_rescored(path)


def complete(name: str) -> bool:
    """A run is analysed only when its rescored file exists and the manifest log says
    COMPLETE (when the log has no line for it, the rescored file alone is accepted)."""
    st = run_status().get(name)
    return (RESCORED / f"{name}.jsonl").exists() and st in (None, "COMPLETE")


def rows_of(name: str) -> list[dict[str, Any]] | None:
    if not complete(name):
        return None
    got = _load(name)
    return None if got is None else got[1]


def prov_of(name: str) -> dict[str, Any] | None:
    got = _load(name) if complete(name) else None
    return None if got is None else got[0]


# ------------------------------------------------------------------ per-case helpers


def by_case(
    rows: Sequence[dict[str, Any]], value: Callable[[dict[str, Any]], float | None]
) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        v = value(r)
        if v is not None:
            out[r["case_id"]].append(float(v))
    return dict(out)


def itt_keys(rows: Sequence[dict[str, Any]], score: str) -> dict[Hashable, float]:
    """(case, rep) -> ITT score (the input of eval.stats contrasts)."""
    return {(r["case_id"], r["rep"]): v for r in rows if (v := itt(r, score)) is not None}


def ci_mean(
    rows: Sequence[dict[str, Any]], value: Callable[[dict[str, Any]], float | None]
) -> tuple[float, float, float] | None:
    return bootstrap_mean(by_case(rows, value))


def resample_idx(n_keys: int) -> np.ndarray:
    """The SAME resamples as eval.stats (seed 20260930, 10k)."""
    return np.random.default_rng(BOOT_SEED).integers(0, n_keys, size=(BOOT_N, n_keys))


def paired_ratio(
    a: Mapping[str, list[float]], b: Mapping[str, list[float]]
) -> tuple[float, float, float, int] | None:
    """(ratio of means a/b, lo, hi, n cases): per-case means over reps, cases both have,
    paired cluster bootstrap (case ids resampled together)."""
    keys = sorted(set(a) & set(b), key=str)
    if not keys:
        return None
    x = np.array([mean(a[k]) for k in keys])
    y = np.array([mean(b[k]) for k in keys])
    if y.sum() <= 0:
        return None
    idx = resample_idx(len(keys))
    ratios = x[idx].sum(axis=1) / np.maximum(y[idx].sum(axis=1), 1e-300)
    lo, hi = np.percentile(ratios, [2.5, 97.5])
    return float(x.sum() / y.sum()), float(lo), float(hi), len(keys)


def fmt(ci: Sequence[float] | None, scale: float = 100.0, digits: int = 1) -> str:
    if ci is None:
        return "-"
    p, lo, hi = (scale * float(v) for v in ci[:3])
    return f"{p:.{digits}f} [{lo:.{digits}f}, {hi:.{digits}f}]"


def fms(ci: Sequence[float] | None) -> str:
    """Latency CI in ms with adaptive precision (sub-10 ms values keep 2 decimals)."""
    if ci is None:
        return "-"
    d = 2 if float(ci[0]) < 10 else 0
    return fmt(ci, 1.0, d)


def fnum(x: float | None, scale: float = 100.0, digits: int = 1) -> str:
    return (
        "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{scale * x:.{digits}f}"
    )


def md_table(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out + [""]


def ci_json(ci: Sequence[float] | None) -> dict[str, float] | None:
    if ci is None:
        return None
    return {"point": float(ci[0]), "lo": float(ci[1]), "hi": float(ci[2])}


# ------------------------------------------------------------------ cost regimes


@lru_cache(maxsize=1)
def bedrock_prices() -> dict[str, dict[str, float]]:
    data = yaml.safe_load(PRICES.read_text(encoding="utf-8")) or {}
    return {
        k: {kk: float(vv) / 1e6 for kk, vv in v.items()}
        for k, v in (data.get("bedrock") or {}).items()
    }


def _steps(row: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for lv in ("skill", "tool"):
        for st in (row.get(lv) or {}).get("steps") or []:
            out.append((lv, st))
    return out


def step_list_uncached(st: dict[str, Any]) -> tuple[float, bool]:
    """(US$ at list price without prompt cache, reported_instead) for one consulted step.
    Bedrock models: tokens x prices.yaml rates. Jev (OpenRouter meta-router) has no list
    price: its reported cost is used and flagged. Local strategies cost 0."""
    u = st.get("usage") or {}
    model = u.get("served_model")
    prices = bedrock_prices()
    if u.get("provider") == "bedrock" and model in prices:
        p = prices[model]
        return p["input"] * u.get("prompt_tokens", 0) + p["output"] * u.get(
            "completion_tokens", 0
        ), False
    if st.get("strategy") == "jev":
        return float(st.get("cost_usd") or 0.0), True
    return 0.0, False


def row_list_uncached(row: dict[str, Any]) -> tuple[float, bool]:
    total, flagged = 0.0, False
    for _, st in _steps(row):
        c, f = step_list_uncached(st)
        total += c
        flagged |= f
    if row.get("mode") == "e2e":
        tok = row.get("tokens") or {}
        models = (row.get("executor") or {}).get("served_models") or []
        prices = bedrock_prices()
        if models and models[0] in prices and tok.get("agent_calls"):
            p = prices[models[0]]
            total += p["input"] * tok.get("prompt", 0) + p["output"] * tok.get("completion", 0)
    return total, flagged


def prefix_sizes(all_rows: Sequence[dict[str, Any]]) -> dict[tuple[str, str, int], int]:
    """Cacheable prompt-prefix tokens per (model, level, static_chars): the largest
    cache_read + cache_write ever observed for that prompt prefix (0 = never cached, e.g.
    below the provider's minimum cacheable length)."""
    out: dict[tuple[str, str, int], int] = {}
    for r in all_rows:
        for lv, st in _steps(r):
            u = st.get("usage") or {}
            if u.get("provider") != "bedrock":
                continue
            k = (u.get("served_model"), lv, int(u.get("static_chars") or 0))
            out[k] = max(
                out.get(k, 0), int(u.get("cache_read") or 0) + int(u.get("cache_write") or 0)
            )
    return out


TTL_S = 300.0
QPS_GRID = (0.01, 0.1, 1.0, 10.0)


def modelled_cache_cost(
    rows: Sequence[dict[str, Any]], qps: float, prefixes: Mapping[tuple[str, str, int], int]
) -> float | None:
    """Mean routing US$/case under a modelled prompt-cache regime: requests arrive as a
    Poisson process at `qps`; a Bedrock prompt prefix p used by a share s_p of cases gets
    rate qps*s_p, and the 5-minute TTL (refreshed on every hit) gives hit probability
    h = 1 - exp(-qps*s_p*300). Each call pays h*C*read + (1-h)*C*write + (P-C)*input +
    out*output (C = cacheable prefix tokens observed for p). Jev: reported cost; local: 0."""
    if not rows:
        return None
    prices = bedrock_prices()
    count: dict[tuple[str, str, int], int] = defaultdict(int)
    for r in rows:
        for lv, st in _steps(r):
            u = st.get("usage") or {}
            if u.get("provider") == "bedrock":
                count[(u.get("served_model"), lv, int(u.get("static_chars") or 0))] += 1
    n = len(rows)
    total = 0.0
    for r in rows:
        for lv, st in _steps(r):
            u = st.get("usage") or {}
            if u.get("provider") == "bedrock" and u.get("served_model") in prices:
                p = prices[u["served_model"]]
                k = (u["served_model"], lv, int(u.get("static_chars") or 0))
                c = prefixes.get(k, 0)
                pt = int(u.get("prompt_tokens") or 0)
                c = min(c, pt)
                h = 1.0 - math.exp(-qps * count[k] / n * TTL_S) if math.isfinite(qps) else 1.0
                total += (
                    h * c * p["cache_read"]
                    + (1 - h) * c * p["cache_write"]
                    + (pt - c) * p["input"]
                    + int(u.get("completion_tokens") or 0) * p["output"]
                )
            elif st.get("strategy") == "jev":
                total += float(st.get("cost_usd") or 0.0)
    return total / n


# ------------------------------------------------------------------ confidence helpers


def raw_conf(st: dict[str, Any]) -> float | None:
    u = st.get("usage") or {}
    for k in ("raw_confidence", "confidence_raw"):
        if u.get(k) is not None:
            return float(u[k])
    return None


def resolving_step(stage: dict[str, Any] | None) -> dict[str, Any] | None:
    if not stage:
        return None
    rb = stage.get("resolved_by")
    steps = stage.get("steps") or []
    for st in steps:
        if st.get("strategy") == rb:
            return st
    return steps[-1] if steps else None


@lru_cache(maxsize=1)
def dev_maps() -> dict[str, dict[str, tuple[np.ndarray, np.ndarray]]]:
    """served model id -> level -> isotonic (x, y) dev map of the canonical P0 prompt
    (config/prompt_selection.yaml), applied or not."""
    data = yaml.safe_load(PROMPT_SELECTION.read_text(encoding="utf-8")) or {}
    out: dict[str, dict[str, tuple[np.ndarray, np.ndarray]]] = {}
    for mid, m in (data.get("models") or {}).items():
        calib = ((m or {}).get("canonical") or {}).get("calibration") or {}
        out[mid] = {
            lv: (np.asarray(v["x"], float), np.asarray(v["y"], float))
            for lv, v in calib.items()
            if isinstance(v, dict) and "x" in v
        }
    return out


def multi_label(exp: Mapping[str, Any]) -> bool:
    return len(exp.get("acceptable_skills") or []) > 1 or len(exp.get("acceptable_tools") or []) > 1


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(path: Path, obj: Any) -> Path:
    return write(path, json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n")


@dataclass
class Context:
    """Loaded runs shared by every section."""

    routing: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    e2e: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    runs: dict[str, Run] = field(default_factory=dict)
    e2e_runs: dict[str, Run] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> Context:
        ctx = cls()
        for r in ROUTING:
            rows = rows_of(r.name)
            if rows is None:
                ctx.missing.append(r.name)
            else:
                ctx.routing[r.key], ctx.runs[r.key] = rows, r
        for r in E2E:
            rows = rows_of(r.name)
            if rows is None:
                ctx.missing.append(r.name)
            else:
                ctx.e2e[r.key], ctx.e2e_runs[r.key] = rows, r
        return ctx
