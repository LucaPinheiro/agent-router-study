"""RQ5 leave-tools-out table (docs/rq5-design.md): accuracy on the held-out tools' cases,
regressions on every other case and the effort of adding the tools, per strategy x condition.

Input: the rescored rows of manifest runs named `rq5-<split>-<strategy>-<condition>` (conditions
base | zero | eng | full). Conditions differ only by manifest `overrides` (catalog exclusion,
regex rules/overlays), so the rows come from the same runner/scorer as every other run.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

from routing_study.eval.rescore import load_tools, read_rescored

EFFORT = Path("config/rq5/effort.yaml")
CONDITIONS = ("base", "zero", "eng", "full")
RUN_NAME = re.compile(
    r"^rq5-(?P<split>[a-z0-9_]+)-(?P<strategy>[a-z0-9_]+)-(?P<cond>base|zero|eng|full)$"
)


def effort_record(path: Path = EFFORT) -> dict[str, Any]:
    return yaml.safe_load(path.read_text("utf-8"))


def held_out_tools(path: Path = EFFORT) -> list[str]:
    return list(effort_record(path)["held_out"])


# ---------------------------------------------------------------- rows


@dataclass(frozen=True)
class RunKey:
    split: str
    strategy: str
    cond: str


def parse_run(name: str) -> RunKey | None:
    m = RUN_NAME.match(name)
    return RunKey(m["split"], m["strategy"], m["cond"]) if m else None


def load_rq5_rows(names: list[str], rescored_dir: Path) -> dict[RunKey, dict[str, dict]]:
    """RunKey -> case_id -> rep-1 row, for the rq5 runs among `names` that were rescored."""
    out: dict[RunKey, dict[str, dict]] = {}
    for name in names:
        key = parse_run(name)
        path = rescored_dir / f"{name}.jsonl"
        if key is None or not path.exists():
            continue
        _, rows = read_rescored(path)
        out[key] = {r["case_id"]: r for r in rows if int(r.get("rep", 1)) == 1}
    return out


def _score(row: dict[str, Any], metric: str) -> float:
    return float((row.get("scores") or {}).get(metric) or 0.0)  # error rows: wrong (ITT)


def _tool(row: dict[str, Any]) -> str | None:
    return (row.get("tool") or {}).get("choice")


def is_affected(row: dict[str, Any], held: set[str]) -> bool:
    return bool(set(row["expected"]["acceptable_tools"]) & held)


def condition_stats(
    rows: dict[str, dict], base: dict[str, dict] | None, held: set[str]
) -> dict[str, Any]:
    """Accuracy on affected cases; regressions on the other cases relative to `base`."""
    aff = [r for r in rows.values() if is_affected(r, held)]
    oth = [r for r in rows.values() if not is_affected(r, held)]

    def acc(rs: list[dict], metric: str) -> float | None:
        return mean(_score(r, metric) for r in rs) if rs else None

    out: dict[str, Any] = {
        "n_aff": len(aff),
        "joint_aff": acc(aff, "joint_correct"),
        "skill_aff": acc(aff, "skill_correct"),
        "pred_held_aff": mean(_tool(r) in held for r in aff) if aff else None,
        "n_oth": len(oth),
        "joint_oth": acc(oth, "joint_correct"),
        "stolen": sum(_tool(r) in held for r in oth),
        "errors": sum(bool(r.get("error")) for r in rows.values()),
    }
    if base is not None:
        paired = [(r, base[r["case_id"]]) for r in oth if r["case_id"] in base]
        lost = sum(_score(b, "joint_correct") > _score(r, "joint_correct") for r, b in paired)
        won = sum(_score(b, "joint_correct") < _score(r, "joint_correct") for r, b in paired)
        out |= {
            "paired": len(paired),
            "lost": lost,
            "won": won,
            "delta_oth_pp": 100 * (won - lost) / len(paired) if paired else None,
        }
    return out


# ---------------------------------------------------------------- effort


def catalog_effort(held: list[str], tools_path: Path | None = None) -> dict[str, int]:
    """Authoring cost of the held-out tools' catalog entries (every strategy's input):
    description lines, `_meta` examples and keywords."""
    tools = {t["name"]: t for t in (load_tools(tools_path) if tools_path else load_tools())}
    lines = examples = keywords = 0
    for name in held:
        t = tools[name]
        meta = t.get("_meta") or {}
        lines += sum(1 for ln in t["description"].splitlines() if ln.strip())
        examples += len(meta.get("br.routingstudy/examples") or [])
        keywords += len(meta.get("br.routingstudy/keywords") or [])
    return {"description_lines": lines, "examples": examples, "keywords": keywords}


def rules_effort(path: Path) -> dict[str, int]:
    """Non-comment, non-blank lines, rules and defs of a regex rules file/overlay."""
    text = Path(path).read_text("utf-8")
    data = yaml.safe_load(text) or {}
    return {
        "lines": sum(1 for ln in text.splitlines() if ln.strip() and ln.lstrip()[0] != "#"),
        "rules": sum(len(v or []) for v in (data.get("rules") or {}).values()),
        "defs": len(data.get("defs") or {}),
    }


def engineered_minutes(rec: dict[str, Any]) -> float:
    from datetime import datetime

    eng = rec["engineered"]
    start, end = (datetime.fromisoformat(eng[k].replace("Z", "+00:00")) for k in ("start", "end"))
    return round((end - start).total_seconds() / 60, 1)


async def retrain_seconds(config: Path, held: list[str]) -> dict[str, float]:
    """Seconds to rebuild the free routers for the full catalog after the add (fresh router
    instances, no in-memory fit cache): BM25 index build and classifier fit over every stage's
    option list (document vectors warm on disk), and the embedding of the NEW option texts
    (texts of the full catalog absent from the reduced one) with a cold vector cache."""
    import tempfile

    from fastmcp import Client
    from mcp_server.server import mcp

    from routing_study.catalog import PROTOCOL_VERSION, fetch_catalog
    from routing_study.routers.base import GLOBAL_OPTION
    from routing_study.routers.pipeline import build_routers
    from routing_study.settings import load_settings

    settings = load_settings(config)
    full = await fetch_catalog(settings, Client(mcp, mode=PROTOCOL_VERSION))
    reduced = full.without(held)

    def stages(cat: Any) -> list[list[Any]]:
        skills = [o.id for o in cat.skill_options() if o.id != GLOBAL_OPTION]
        return [cat.skill_options(), *(cat.tool_options(s) for s in skills)]

    out: dict[str, float] = {}
    routers = build_routers(settings, {"bm25", "classifier", "embedding"})
    t = time.perf_counter()
    for opts in stages(full):
        routers["bm25"]._bm25(opts)
    out["bm25"] = time.perf_counter() - t
    clf = routers["classifier"]
    for opts in stages(full):  # warm the document vectors so only the fit is timed
        await clf.embedding.text_vectors(clf.training_set(opts)[0])  # type: ignore[union-attr]
    clf._fitted.clear()
    t = time.perf_counter()
    for opts in stages(full):
        await clf._fit(opts)
    out["classifier"] = time.perf_counter() - t
    emb = routers["embedding"]
    old = {x for opts in stages(reduced) for o in opts for x in emb.option_texts(o)}
    new = sorted({x for opts in stages(full) for o in opts for x in emb.option_texts(o)} - old)
    with tempfile.TemporaryDirectory() as tmp:
        cold = build_routers(settings.model_copy(update={"cache_dir": tmp}), {"embedding"})
        t = time.perf_counter()
        await cold["embedding"].text_vectors(new)
        out["embedding"] = time.perf_counter() - t
    out["embedding_new_texts"] = float(len(new))
    return out


# ---------------------------------------------------------------- table


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:.1f}"


def render(
    data: dict[RunKey, dict[str, dict]],
    held: list[str],
    split: str,
    retrain: dict[str, float] | None = None,
) -> str:
    hs = set(held)
    by_strategy: dict[str, dict[str, dict]] = defaultdict(dict)
    for k, rows in data.items():
        if k.split == split:
            by_strategy[k.strategy][k.cond] = rows
    rec = effort_record()
    eng = rules_effort(Path(rec["engineered"]["overlay"]))
    orig = rules_effort(Path("config/rq5/regex_overlay_original.yaml"))
    cat = catalog_effort(held)
    lines = [
        f"## RQ5 leave-tools-out — split `{split}`",
        "",
        f"Held out: {', '.join(f'`{h}`' for h in held)}. affected = cases with a held-out tool "
        "among the acceptable tools; other = the rest. Δ other / lost / won are paired with "
        "`base` (joint, other cases); stolen = other cases routed to a held-out tool. "
        "Errors count as wrong (ITT).",
        "",
        "| strategy | cond | n aff | joint aff | skill aff | pred∈H aff | n other | joint other "
        "| lost | won | Δ other (pp) | stolen | errors |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for strategy in sorted(by_strategy):
        conds = by_strategy[strategy]
        base = conds.get("base")
        for cond in CONDITIONS:
            if cond not in conds:
                continue
            s = condition_stats(conds[cond], base if cond != "base" else None, hs)
            delta = s.get("delta_oth_pp")
            lines.append(
                f"| {strategy} | {cond} | {s['n_aff']} | {_pct(s['joint_aff'])} | "
                f"{_pct(s['skill_aff'])} | {_pct(s['pred_held_aff'])} | {s['n_oth']} | "
                f"{_pct(s['joint_oth'])} | {s.get('lost', '–')} | {s.get('won', '–')} | "
                f"{'–' if delta is None else f'{delta:+.1f}'} | {s['stolen']} | {s['errors']} |"
            )
    lines += [
        "",
        "### Effort of adding the 3 tools",
        "",
        f"- Catalog entry (input of every strategy, the zero-effort add): "
        f"{cat['description_lines']} description lines, {cat['examples']} examples, "
        f"{cat['keywords']} keywords.",
        f"- Regex, engineered (`eng`): {eng['lines']} lines, {eng['rules']} rules, "
        f"{eng['defs']} defs, {engineered_minutes(rec)} min wall clock "
        f"(timebox {rec['engineered']['timebox_min']} min; {rec['engineered']['author']}).",
        f"- Regex, production (`full`, reference): {orig['lines']} lines, {orig['rules']} "
        f"rules, {orig['defs']} defs; minutes not recorded (iterated on dev).",
        "- Regex, zero-effort: nothing new (the tool is unreachable by regex).",
    ]
    if retrain:
        lines.append(
            "- Re-train after the add (s): "
            f"BM25 index {retrain['bm25']:.3f}, classifier fit {retrain['classifier']:.3f}, "
            f"embedding of {int(retrain['embedding_new_texts'])} new option texts (cold) "
            f"{retrain['embedding']:.2f}; hybrid = classifier fit + regex (0); LLM/Jev 0 "
            "(prompt rebuilt from the catalog)."
        )
    return "\n".join(lines) + "\n"
