"""Secondary metrics of the report (F6, methodology-final M4/M5, minor 3-5). Definitions are
in docs/metrics.md; every function takes rescored rows or plain (confidence, correct) pairs.

- `recall_at_k`: an acceptable tool is among the router's top-k tool candidates (the choice
  first, then the recorded candidates), with a correct skill; out-of-scope golds accept
  `escalate_to_human`. Error rows count 0 (ITT).
- `abstention_pr`: precision / recall of abstaining (a routed or host abstention, or
  escalation as the only action) against golds that EXPECT abstention.
- `risk_coverage`: selective prediction over rows ranked by confidence (highest first):
  the curve, AURC (mean risk over coverages 1/n..1) and the largest coverage whose risk is
  <= a target (5%). Error rows are kept with confidence 0 and counted wrong (ITT).
- `calibration`: Brier score and adaptive-bin (equal-mass) ECE with the bin counts.
- `baselines`: trivial routers on a split, scored by the shared scorer: always escalate,
  majority class per stage (skill, then tool within it; fitted on dev) and the expectation
  of uniform random choice over each stage's options.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from statistics import mean
from typing import Any

import numpy as np

from routing_study.eval.scorers import (
    ESCALATE,
    allows_abstention,
    expects_abstention,
    routing_scores,
)
from routing_study.routers.base import ABSTAIN, GLOBAL_OPTION

RISK_TARGET = 0.05
ECE_BINS = 10


# ---------------------------------------------------------------- per-row helpers


def ranked_tools(row: dict[str, Any]) -> list[str]:
    """The router's tool ranking: its choice first, then the recorded candidates."""
    tool = row.get("tool") or {}
    out: list[str] = []
    for t in [tool.get("choice"), *(c[0] for c in tool.get("candidates") or [])]:
        if t and t not in out:
            out.append(t)
    return out


def recall_at_k(row: dict[str, Any], k: int) -> float | None:
    """1 if an acceptable tool is in the top-k with a correct skill; None for native rows."""
    if row.get("native") or not row.get("expected"):
        return None
    if row.get("error"):
        return 0.0
    exp = row["expected"]
    if not (row.get("scores") or {}).get("skill_correct"):
        return 0.0
    ok = set(exp["acceptable_tools"]) | (
        {ESCALATE} if ABSTAIN in exp["acceptable_tools"] else set()
    )
    if ABSTAIN in exp["acceptable_tools"] and not ranked_tools(row):
        return 1.0  # abstained on an out-of-scope gold
    return float(bool(ok & set(ranked_tools(row)[:k])))


def abstained(row: dict[str, Any]) -> bool:
    """The row abstained: routed abstention, host abstention or escalation as the only
    business action (the `abstain_correct` definition)."""
    if row.get("error"):
        return False
    if row.get("mode") == "routing-only":
        tool = (row.get("tool") or {}).get("choice")
        skill = (row.get("skill") or {}).get("choice")
        return not skill or not tool or tool == ESCALATE
    if row.get("outcome") == "abstained":
        return True
    calls = [c for c in row.get("calls") or [] if c.get("name") != "load_skill"]
    return bool(calls) and all(c["name"] == ESCALATE for c in calls)


def abstention_pr(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Precision = abstentions whose gold allows it; recall = abstentions among golds that
    expect it (only abstention / escalation acceptable)."""
    rows = [r for r in rows if r.get("expected")]
    pred = [r for r in rows if abstained(r)]
    gold = [r for r in rows if expects_abstention(r["expected"])]
    return {
        "n_abstained": len(pred),
        "n_expected": len(gold),
        "precision": mean(float(allows_abstention(r["expected"])) for r in pred) if pred else None,
        "recall": mean(float(abstained(r)) for r in gold) if gold else None,
    }


def joint_confidence(row: dict[str, Any]) -> float:
    """Recorded confidence of the routed decision: min(skill, tool) (0 for errors and
    abstentions)."""
    if row.get("error"):
        return 0.0
    confs = [float((row.get(s) or {}).get("confidence") or 0.0) for s in ("skill", "tool")]
    if not (row.get("tool") or {}).get("choice"):
        confs = confs[:1]
    return min(confs) if confs else 0.0


# ---------------------------------------------------------------- selective prediction


def risk_coverage(
    pairs: Iterable[tuple[float, float]], target: float = RISK_TARGET
) -> dict[str, Any] | None:
    """(confidence, correct) -> {'coverage', 'risk' (curves), 'aurc', 'coverage_at_risk'}.
    Ties in confidence enter together (one curve point per distinct confidence)."""
    data = sorted(((float(c), float(ok)) for c, ok in pairs), key=lambda t: -t[0])
    if not data:
        return None
    n = len(data)
    conf = np.array([c for c, _ in data])
    wrong = 1.0 - np.array([ok for _, ok in data])
    cum = np.cumsum(wrong)
    ends = [i for i in range(n) if i == n - 1 or conf[i + 1] != conf[i]]
    coverage = [(i + 1) / n for i in ends]
    risk = [float(cum[i] / (i + 1)) for i in ends]
    # AURC: every row position, a tie block taking its block's risk
    per_row = np.empty(n)
    start = 0
    for i, r in zip(ends, risk, strict=True):
        per_row[start : i + 1] = r
        start = i + 1
    ok_cov = [c for c, r in zip(coverage, risk, strict=True) if r <= target + 1e-12]
    return {
        "coverage": coverage,
        "risk": risk,
        "aurc": float(per_row.mean()),
        "coverage_at_risk": max(ok_cov) if ok_cov else 0.0,
        "target": target,
    }


def calibration(
    pairs: Iterable[tuple[float, float]], bins: int = ECE_BINS
) -> dict[str, Any] | None:
    """Brier score and adaptive (equal-mass) ECE; `bins` lists (n, mean conf, accuracy)."""
    data = sorted((float(c), float(ok)) for c, ok in pairs)
    if not data:
        return None
    conf = np.array([c for c, _ in data])
    ok = np.array([o for _, o in data])
    groups = [g for g in np.array_split(np.arange(len(data)), min(bins, len(data))) if len(g)]
    table = [(len(g), float(conf[g].mean()), float(ok[g].mean())) for g in groups]
    ece = sum(n / len(data) * abs(c - a) for n, c, a in table)
    return {
        "n": len(data),
        "brier": float(np.mean((conf - ok) ** 2)),
        "ece": float(ece),
        "bins": table,
    }


def level_pairs(rows: Sequence[dict[str, Any]], level: str) -> list[tuple[float, float]]:
    """(recorded confidence, correct) of the decisions a level made (abstentions and error
    rows out): skill -> skill_correct; tool -> tool_correct on rows with a correct skill."""
    out = []
    for r in rows:
        d = r.get(level) or {}
        s = r.get("scores") or {}
        if r.get("error") or not d.get("choice"):
            continue
        if level == "tool" and not s.get("skill_correct"):
            continue
        key = "skill_correct" if level == "skill" else "tool_correct"
        if s.get(key) is not None:
            out.append((float(d.get("confidence") or 0.0), float(s[key])))
    return out


# ---------------------------------------------------------------- trivial baselines


def _first(expected: Mapping[str, Any], key: str) -> str:
    return (expected.get(key) or [ABSTAIN])[0]


def majority_router(dev: Sequence[Mapping[str, Any]]) -> tuple[str, dict[str, str]]:
    """(majority skill, skill -> majority tool) from the dev golds' first labels."""
    skills = Counter(_first(c["expected"], "acceptable_skills") for c in dev)
    tools: dict[str, Counter[str]] = {}
    for c in dev:
        s = _first(c["expected"], "acceptable_skills")
        tools.setdefault(s, Counter())[_first(c["expected"], "acceptable_tools")] += 1
    top = skills.most_common(1)[0][0] if skills else ABSTAIN
    return top, {s: cnt.most_common(1)[0][0] for s, cnt in tools.items()}


def baselines(
    cases: Sequence[Mapping[str, Any]],
    dev: Sequence[Mapping[str, Any]],
    skill_tools: Mapping[str, Sequence[str]],
) -> dict[str, dict[str, float]]:
    """name -> {metric: mean over cases} for the trivial routers. `skill_tools` maps each
    business skill to its tools; `__global__` holds the global tools (offered at every tool
    stage, and the only tools after a `__global__` skill), as in the host."""
    maj_skill, maj_tool = majority_router(dev)
    global_tools = list(skill_tools.get(GLOBAL_OPTION, ()))
    skill_options = [s for s in skill_tools if s != GLOBAL_OPTION] + [GLOBAL_OPTION]

    def tools_for(skill: str) -> list[str]:
        own = [] if skill == GLOBAL_OPTION else list(skill_tools.get(skill, ()))
        return own + global_tools

    out: dict[str, list[dict[str, float]]] = {"always_escalate": [], "majority": [], "uniform": []}
    for c in cases:
        exp = c["expected"]
        out["always_escalate"].append(routing_scores(GLOBAL_OPTION, ESCALATE, exp))
        tool = maj_tool.get(maj_skill) or (global_tools[0] if global_tools else None)
        out["majority"].append(routing_scores(maj_skill, tool, exp))
        expect: dict[str, float] = Counter()  # type: ignore[assignment]
        for s in skill_options:
            opts = tools_for(s) or [None]
            for t in opts:
                for k, v in routing_scores(s, t, exp).items():
                    expect[k] += v / (len(skill_options) * len(opts))
        out["uniform"].append(dict(expect))
    return {name: {k: mean(r[k] for r in rs) for k in rs[0]} for name, rs in out.items() if rs}


def skill_tools_of(tools: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    """skill -> tool names from MCP tools/list `_meta` (global tools under `__global__`)."""
    out: dict[str, list[str]] = {}
    for t in tools:
        skill = (t.get("_meta") or {}).get("br.routingstudy/skill") or GLOBAL_OPTION
        out.setdefault(skill, []).append(t["name"])
    return out
