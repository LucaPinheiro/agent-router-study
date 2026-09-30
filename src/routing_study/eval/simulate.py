"""Offline cascade: replay a config's pipeline over the shadow decisions saved by a shadow run.

The same `RoutingPipeline` code decides, fed by routers that return the recorded decisions, so
the simulation cannot drift from the online logic, and the same shared scorer
(`scorers.routing_scores`) scores it as a real run (H1). Cost and latency are the ORIGINAL
values of the consulted steps (a cached hit counts what it cost when first computed).

Per row (H2, M4):
- error: the replayed stage had no accepting step and a consulted decision failed
  (`usage.error` or `parse_fail`): excluded, never a scored abstention;
- the simulated skill cannot be correct: skill, tool and joint are 0 (the tool stage is not
  needed to know that);
- the skill can be correct and the recorded run routed to the same skill: the tool stage is
  replayed and scored;
- the skill can be correct but differs from the recorded one: `tool_unavailable` (joint and
  cost unknown). The headline `joint_acc` is over ALL non-error rows with unavailable rows
  counted as 0 (a lower bound); `joint_acc_covered` excludes them.
Cost/latency are over covered rows (whole route simulated) only, labelled as such.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from routing_study.eval.report import load_results
from routing_study.eval.scorers import routing_failure, routing_scores, skill_can_be_correct
from routing_study.routers.base import ABSTAIN, RouteDecision, RouteOption, RoutingInput
from routing_study.routers.pipeline import RoutingPipeline
from routing_study.settings import Settings, StageConfig


class _Replay:
    def __init__(self, name: str, decision: RouteDecision) -> None:
        self.name = name
        self.decision = decision

    async def route(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        return self.decision


def replay_stage(
    stage: StageConfig, shadow: dict[str, Any], *, mode: str, level: str
) -> dict[str, Any] | None:
    """Simulated decision for one stage, or None if a pipeline strategy was not recorded."""
    if not stage.pipeline or any(s.strategy not in shadow for s in stage.pipeline):
        return None
    routers = {k: _Replay(k, RouteDecision.model_validate(v)) for k, v in shadow.items()}
    pipeline = RoutingPipeline(stage, routers, mode="single" if mode == "single" else "cascade")
    res = asyncio.run(pipeline.run(RoutingInput(message="", level=level), []))  # type: ignore[arg-type]
    steps = [s.model_dump(mode="json") for s in res.steps]
    return {
        "choice": res.decision.choice or ABSTAIN,
        "confidence": res.decision.confidence,
        "resolved_by": res.resolved_by or "abstained",
        "error": routing_failure(steps, res.resolved_by is not None),
        "cost_usd": sum(s.cost_usd for s in res.steps),
        "latency_ms": sum(s.latency_ms for s in res.steps),
    }


def simulate_rows(rows: list[dict[str, Any]], settings: Settings) -> list[dict[str, Any]]:
    """One result per shadow row (see module docstring); key = (case_id, rep)."""
    mode = settings.routing.mode
    out = []
    for r in rows:
        base = {"key": (r["case_id"], r["rep"]), "case_id": r["case_id"]}
        base["category"] = r.get("category")
        if not (r.get("skill") or {}).get("shadow"):
            out.append(base | {"error": r.get("error") or "no shadow decisions"})
            continue
        exp = r["expected"]
        sk = replay_stage(settings.routing.skill, r["skill"]["shadow"], mode=mode, level="skill")
        if sk is None:
            raise ValueError("skill pipeline strategy not recorded in the shadow run")
        row = base | {
            "error": sk["error"],
            "resolved_by": sk["resolved_by"],
            "confidence": sk["confidence"],
            "skill_choice": sk["choice"],
            "tool_unavailable": False,
            "cost_usd": None,
            "latency_ms": None,
        }
        if sk["error"]:
            out.append(row)
            continue
        cost, lat = sk["cost_usd"], sk["latency_ms"]
        tl: dict[str, Any] | None = None
        if sk["choice"] != ABSTAIN and skill_can_be_correct(sk["choice"], exp):
            recorded = (r["skill"].get("choice") or ABSTAIN) == sk["choice"]
            if recorded and (r.get("tool") or {}).get("shadow"):
                tl = replay_stage(
                    settings.routing.tool, r["tool"]["shadow"], mode=mode, level="tool"
                )
            if tl is None:
                row |= {
                    "tool_unavailable": True,
                    "skill_correct": float(sk["choice"] in exp["acceptable_skills"]),
                    "joint_correct": None,
                }
                out.append(row)
                continue
            if tl["error"]:
                out.append(row | {"error": tl["error"]})
                continue
            cost, lat = cost + tl["cost_usd"], lat + tl["latency_ms"]
        elif sk["choice"] != ABSTAIN:  # wrong skill: tool/joint are 0 whatever the tool
            tr = (r.get("tool") or {}).get("shadow")
            if (r["skill"].get("choice") or ABSTAIN) == sk["choice"] and tr:
                tl = replay_stage(settings.routing.tool, tr, mode=mode, level="tool")
            if tl is None or tl["error"]:
                cost = lat = None  # type: ignore[assignment]
            else:
                cost, lat = cost + tl["cost_usd"], lat + tl["latency_ms"]
        s = routing_scores(sk["choice"], tl["choice"] if tl else None, exp)
        if not skill_can_be_correct(sk["choice"], exp):
            s = s | {"tool_correct": 0.0, "joint_correct": 0.0}
        out.append(row | s | {"cost_usd": cost, "latency_ms": lat})
    return out


def aggregate(results: list[dict[str, Any]], keys: set[Any] | None = None) -> dict[str, Any]:
    """Accuracy over non-error rows (restricted to `keys` when given), cost over covered rows."""
    rows = [x for x in results if not x["error"] and (keys is None or x["key"] in keys)]
    covered = [x for x in rows if x["cost_usd"] is not None]
    known = [x["joint_correct"] for x in rows if x.get("joint_correct") is not None]
    unavailable = sum(1 for x in rows if x["tool_unavailable"])
    return {
        "n": len(rows),
        "errors": sum(1 for x in results if x["error"]),
        "skill_acc": mean(x["skill_correct"] for x in rows) if rows else None,
        "joint_acc": sum(known) / len(rows) if rows else None,
        "joint_acc_covered": mean(known) if known else None,
        "tool_unavailable": unavailable,
        "tool_coverage": 1 - unavailable / len(rows) if rows else None,
        "covered_n": len(covered),
        "routing_cost_case": mean(x["cost_usd"] for x in covered) if covered else None,
        "routing_ms_case": mean(x["latency_ms"] for x in covered) if covered else None,
        "resolved_by": dict(Counter(x["resolved_by"] for x in rows)),
    }


def simulate(results: Path, settings: Settings) -> dict[str, Any]:
    rows = load_results([results])
    if not any((r.get("skill") or {}).get("shadow") for r in rows):
        raise ValueError(f"{results} has no shadow decisions (run with --routing-mode shadow)")
    return {"config": settings.experiment_id} | aggregate(simulate_rows(rows, settings))


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.1f}%"


def render_simulation(results: Path, settings: Settings) -> str:
    s = simulate(results, settings)
    cost = (
        f"routing $/case={s['routing_cost_case']:.3e} routing ms/case={s['routing_ms_case']:.0f}"
        if s["routing_cost_case"] is not None
        else "routing $/case=- routing ms/case=-"
    )
    return (
        f"simulated {s['config']} over {results.name}: n={s['n']} errors={s['errors']} "
        f"skill={_pct(s['skill_acc'])} joint={_pct(s['joint_acc'])} (all rows, unavailable=0) "
        f"joint_covered={_pct(s['joint_acc_covered'])} "
        f"tool_coverage={_pct(s['tool_coverage'])} tool_unavailable={s['tool_unavailable']} "
        f"{cost} (covered rows, n={s['covered_n']}) resolved_by={s['resolved_by']}"
    )
