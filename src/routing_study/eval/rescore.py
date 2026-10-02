"""`study rescore`: every published number comes from here (review M2).

Recomputes all scores OFFLINE and deterministically from the raw result rows, the case
turns/expected of `data/dataset_<split>.jsonl` and the MCP tool schemas/annotations of
`mcp_server/tools_list.json`, with the one shared scorer (`eval/scorers.py`). The scores stored
in the raw rows are kept as `raw_scores` / `raw_error` for audit and never read by a report.

Output: one JSONL per input; line 1 is `{"_provenance": {...}}` (scorer hash, dataset and
tools sha256, git sha of the rescoring code, git sha of the run when recorded, else
"unknown"), then one rescored row per raw row, in the same order. Works on rows written
before rows carried provenance fields (no field beyond the E1-E9 row schema is required).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from routing_study.eval.scorers import (
    LOAD_SKILL,
    routing_failure,
    score_turn,
    scorer_hash,
    tool_index,
)

PROVENANCE = "_provenance"
DATA_DIR = Path("data")
TOOLS_LIST = Path("mcp_server/tools_list.json")
EXPERIMENTS_DIR = Path("config/experiments")
UNKNOWN = "unknown (not recorded in rows)"
NA = "n/a"  # a used model has no list price (OpenRouter pricing -1, e.g. the Jev meta-router)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_raw(paths: Iterable[Path]) -> list[dict[str, Any]]:
    """Raw rows (a rescored file's provenance line is skipped)."""
    rows: list[dict[str, Any]] = []
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if PROVENANCE not in row:
                    rows.append(row)
    return rows


def read_rescored(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(provenance, rows) of a rescored file; ValueError for a raw results file."""
    lines = [x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    head = json.loads(lines[0]) if lines else {}
    if PROVENANCE not in head:
        raise ValueError(
            f"{path} is a raw results file: reports read rescored rows only; run "
            f"`uv run study rescore {path} --out results/rescored` first"
        )
    return head[PROVENANCE], [json.loads(x) for x in lines[1:]]


def load_dataset(split: str, data_dir: Path = DATA_DIR) -> tuple[dict[str, dict[str, Any]], Path]:
    path = data_dir / f"dataset_{split}.jsonl"
    cases = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            c = json.loads(line)
            cases[c["id"]] = c
    return cases, path


def load_tools(path: Path = TOOLS_LIST) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["tools"] if isinstance(data, dict) else data


def load_prices(path: Path) -> dict[str, tuple[float, float]]:
    """USD per token (prompt, completion) by slug, from a saved OpenRouter `GET /models`
    (and/or `/embeddings/models`) response, or a flat {slug: {prompt, completion}} map."""
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("data") if isinstance(data, dict) and "data" in data else None
    out: dict[str, tuple[float, float]] = {}
    if items is not None:
        for m in items:
            p = m.get("pricing") or {}
            out[m["id"]] = (float(p.get("prompt") or 0), float(p.get("completion") or 0))
    else:
        for slug, p in data.items():
            out[slug] = (float(p.get("prompt") or 0), float(p.get("completion") or 0))
    return out


def config_models(config: str, experiments_dir: Path = EXPERIMENTS_DIR) -> dict[str, str]:
    """strategy/executor -> model slug from the experiment YAML (read as plain data: no env
    or .env overrides, so the result is the same on every machine)."""
    import yaml

    path = experiments_dir / f"{config}.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {
        k: v["model"]
        for k, v in (data.get("strategies") or {}).items()
        if isinstance(v, dict) and v.get("model")
    }
    if (data.get("executor") or {}).get("model"):
        out["executor"] = data["executor"]["model"]
    return out


def list_price_usd(
    row: dict[str, Any], models: dict[str, str], prices: dict[str, tuple[float, float]]
) -> float | str | None:
    """Cost at list price with NO prompt-cache discount (review L2): consulted router steps
    (each step's recorded tokens) + executor tokens. A failed step that recorded no tokens
    costs 0; `NA` when a used model has a negative (unknown) list price; None when a used
    model has no price at all or a successful paid step recorded no tokens."""
    total = 0.0
    na = False

    def price(model: str | None) -> tuple[float, float] | None:
        nonlocal na
        if model not in prices:
            return None
        pin, pout = prices[model]  # type: ignore[index]
        if pin < 0 or pout < 0:
            na = True
            return 0.0, 0.0
        return pin, pout

    for stage in (row.get("skill"), row.get("tool")):
        for st in (stage or {}).get("steps") or []:
            strategy = st.get("strategy")
            if strategy in ("regex", "bm25"):
                continue
            usage = st.get("usage") or {}
            if "prompt_tokens" not in usage:
                if usage.get("error"):
                    continue  # the call failed before producing tokens
                return None
            pp = price(models.get("embedding" if strategy == "hybrid" else strategy or ""))
            if pp is None:
                return None
            total += pp[0] * usage.get("prompt_tokens", 0) + pp[1] * usage.get(
                "completion_tokens", 0
            )
    tokens = row.get("tokens") or {}
    if row.get("mode") == "e2e" and tokens.get("agent_calls"):
        pp = price(models.get("executor"))
        if pp is None:
            return None
        total += pp[0] * tokens.get("prompt", 0) + pp[1] * tokens.get("completion", 0)
    return NA if na else total


def billed_total(row: dict[str, Any]) -> float:
    """What the run was billed: every routing strategy that ran (in shadow mode the shadow
    strategies too: `shadow_billed_usd`, equal to `billed_usd` outside shadow mode) plus the
    executor (F7)."""
    routing = 0.0
    for st in ("skill", "tool"):
        stage = row.get(st) or {}
        billed = stage.get("shadow_billed_usd")
        routing += float(billed if billed is not None else stage.get("billed_usd") or 0.0)
    return routing + float((row.get("cost_usd") or {}).get("agent") or 0.0)


def row_error(row: dict[str, Any]) -> str | None:
    """The row's error, recomputed. A crashed case (no turn record) keeps its exception; a
    routing error holds only when no consulted step of the stage accepted (finding 2), and a
    parse failure there counts as an error too (M4)."""
    if "calls" not in row:
        return row.get("error") or "no turn record"
    for stage in (row.get("skill"), row.get("tool")):
        if stage:
            err = routing_failure(stage.get("steps") or [], bool(stage.get("resolved_by")))
            if err:
                return err
    return None


def business_rounds(row: dict[str, Any]) -> int:
    """Executor tool rounds without load_skill (one call per round: parallel calls are
    disabled, so this is exact unless a model ignores that flag)."""
    return sum(1 for c in row.get("calls") or [] if c.get("name") != LOAD_SKILL)


def round4_check(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Review M6: rows that used a 4th business round (routed runs get one more than native
    because the +1 for load_skill is added in every mode), per mode. Read-only check: the
    graph is not changed."""
    out: dict[str, Counter[str]] = {}
    for r in rows:
        if r.get("mode") != "e2e" or "calls" not in r:
            continue
        mode = "native" if r.get("native") else "routed"
        c = out.setdefault(mode, Counter())
        c["rows"] += 1
        c["round4_used"] += business_rounds(r) >= 4
    return {k: dict(v) for k, v in out.items()}


def rescore_rows(
    rows: list[dict[str, Any]],
    cases: dict[str, dict[str, Any]],
    tools: list[dict[str, Any]],
    prices: dict[str, tuple[float, float]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rescored rows, checks) for rows of one split."""
    schemas, read_only = tool_index(tools)
    known = set(schemas)
    checks: Counter[str] = Counter()
    models_by_config: dict[str, dict[str, str]] = {}
    out = []
    for raw in rows:
        row = dict(raw)
        row["raw_error"], row["raw_scores"] = raw.get("error"), raw.get("scores")
        case = cases.get(raw.get("case_id", ""))
        if case is None:
            checks["missing_case"] += 1
            row["error"], row["scores"] = "case not in dataset", {}
            out.append(row)
            continue
        if raw.get("expected") != case["expected"]:
            checks["expected_changed"] += 1
        row["expected"] = case["expected"]
        row["error"] = row_error(raw)
        if row["error"] != raw.get("error"):
            checks["error_changed"] += 1
        checks["unknown_tool_calls"] += sum(
            1
            for c in raw.get("calls") or []
            if c.get("name") != LOAD_SKILL and c.get("name") not in known
        )
        row["scores"] = (
            score_turn(raw, case["expected"], schemas, turns=case["turns"], read_only=read_only)
            if "calls" in raw
            else {}
        )
        cost = dict(raw.get("cost_usd") or {})
        cost["billed_total"] = billed_total(raw)
        if prices is not None:
            config = raw.get("config", "")
            models = models_by_config.setdefault(config, config_models(config))
            cost["list_uncached"] = list_price_usd(raw, models, prices)
        row["cost_usd"] = cost
        out.append(row)
    return out, dict(checks)


def rescore_file(
    path: Path,
    out_dir: Path,
    *,
    data_dir: Path = DATA_DIR,
    tools_path: Path = TOOLS_LIST,
    prices_path: Path | None = None,
    run_git_sha: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Rescore one raw results file into `out_dir/<name>.jsonl`; returns (path, provenance).
    `run_git_sha` fills the run's code version for rows written before rows carried it
    (e.g. from the Langfuse trace metadata); it is recorded as given, never guessed."""
    from routing_study.eval.runner import git_sha

    rows = load_raw([path])
    splits = sorted({r.get("split", "") for r in rows})
    if len(splits) != 1:
        raise ValueError(f"{path}: expected rows of one split, got {splits}")
    cases, data_path = load_dataset(splits[0], data_dir)
    tools = load_tools(tools_path)
    prices = load_prices(prices_path) if prices_path else None
    rescored, checks = rescore_rows(rows, cases, tools, prices)

    def recorded(key: str) -> list[str] | str:
        values = sorted({str(r[key]) for r in rows if r.get(key)})
        return values or UNKNOWN

    provenance = {
        "source": {"file": path.name, "sha256": sha256_file(path), "rows": len(rows)},
        "scorer_hash": scorer_hash(),
        "rescore_git_sha": git_sha(),
        "run_git_sha": (
            recorded("git_sha") if any(r.get("git_sha") for r in rows) else run_git_sha or UNKNOWN
        ),
        "run_scorer_hash": recorded("scorer_hash"),
        "run_dataset_sha256": recorded("dataset_sha256"),
        "dataset": {"split": splits[0], "file": data_path.name, "sha256": sha256_file(data_path)},
        "tools": {"file": tools_path.name, "sha256": sha256_file(tools_path)},
        "prices": (
            {"file": prices_path.name, "sha256": sha256_file(prices_path)} if prices_path else None
        ),
        "row_hashes": {k: recorded(k) for k in ("config_hash", "catalog_hash", "prompt_hash")},
        "checks": checks,
        "round4": round4_check(rows),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / path.name
    lines = [json.dumps({PROVENANCE: provenance}, ensure_ascii=False, sort_keys=True)]
    lines += [json.dumps(r, ensure_ascii=False, default=str) for r in rescored]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out, provenance


def describe(out: Path, prov: dict[str, Any]) -> str:
    src = prov["source"]
    r4 = ", ".join(
        f"{mode}: {c.get('round4_used', 0)}/{c.get('rows', 0)} rows used a 4th business round"
        for mode, c in sorted(prov["round4"].items())
    )
    return (
        f"{src['file']} ({src['rows']} rows) -> {out}\n"
        f"  scorer {prov['scorer_hash']} | dataset {prov['dataset']['file']} "
        f"{prov['dataset']['sha256'][:12]} | tools {prov['tools']['sha256'][:12]} | "
        f"rescore git {prov['rescore_git_sha']} | run git {prov['run_git_sha']}\n"
        f"  checks {prov['checks'] or '{}'}\n"
        f"  M6 round-4 check: {r4 or 'no e2e rows'}"
    )
