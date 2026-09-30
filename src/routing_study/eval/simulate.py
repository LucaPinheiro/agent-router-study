"""Offline cascade: replay a config's pipeline over the shadow decisions saved by a shadow run.

The same `RoutingPipeline` code decides, fed by routers that return the recorded decisions, so
the simulation cannot drift from the online logic. Cost and latency are the ORIGINAL values of
the consulted steps (a cached hit counts what it cost when first computed).
"""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from routing_study.eval.report import load_results
from routing_study.routers.base import ABSTAIN, RouteDecision, RouteOption, RoutingInput
from routing_study.routers.pipeline import RoutingPipeline
from routing_study.settings import Settings, StageConfig


class _Replay:
    def __init__(self, name: str, decision: RouteDecision) -> None:
        self.name = name
        self.decision = decision

    async def route(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        return self.decision


def replay_stage(stage: StageConfig, shadow: dict[str, Any], *, mode: str,
                 level: str) -> dict[str, Any] | None:
    """Simulated decision for one stage, or None if a pipeline strategy was not recorded."""
    if not stage.pipeline or any(s.strategy not in shadow for s in stage.pipeline):
        return None
    routers = {k: _Replay(k, RouteDecision.model_validate(v)) for k, v in shadow.items()}
    pipeline = RoutingPipeline(stage, routers, mode="single" if mode == "single" else "cascade")
    res = asyncio.run(pipeline.run(RoutingInput(message="", level=level), []))  # type: ignore[arg-type]
    return {"choice": res.decision.choice or ABSTAIN, "resolved_by": res.resolved_by or "abstained",
            "cost_usd": sum(s.cost_usd for s in res.steps),
            "latency_ms": sum(s.latency_ms for s in res.steps)}


def simulate(results: Path, settings: Settings) -> dict[str, Any]:
    rows = [r for r in load_results([results]) if not r.get("error") and r.get("skill")]
    if not rows or not rows[0]["skill"].get("shadow"):
        raise ValueError(f"{results} has no shadow decisions (run with --routing-mode shadow)")
    mode = settings.routing.mode
    skill_ok: list[float] = []
    tool_ok: list[float] = []
    cost: list[float] = []
    latency: list[float] = []
    resolved: Counter[str] = Counter()
    for r in rows:
        exp = r["expected"]
        sk = replay_stage(settings.routing.skill, r["skill"]["shadow"], mode=mode, level="skill")
        if sk is None:
            raise ValueError(f"skill pipeline strategy not recorded in {results}")
        skill_ok.append(float(sk["choice"] in exp["acceptable_skills"]))
        resolved[sk["resolved_by"]] += 1
        c, lat = sk["cost_usd"], sk["latency_ms"]
        # the tool stage is only comparable when the recorded run routed to the same skill
        if sk["choice"] != ABSTAIN and r.get("tool") and r["skill"]["choice"] == sk["choice"]:
            tl = replay_stage(settings.routing.tool, r["tool"]["shadow"], mode=mode, level="tool")
            if tl is not None:
                tool_ok.append(float(tl["choice"] in exp["acceptable_tools"]))
                c, lat = c + tl["cost_usd"], lat + tl["latency_ms"]
        elif sk["choice"] == ABSTAIN:
            tool_ok.append(float(ABSTAIN in exp["acceptable_tools"]))
        cost.append(c)
        latency.append(lat)
    return {"config": settings.experiment_id, "n": len(rows), "skill_acc": mean(skill_ok),
            "tool_acc": mean(tool_ok) if tool_ok else None, "tool_n": len(tool_ok),
            "routing_cost_case": mean(cost), "routing_ms_case": mean(latency),
            "resolved_by": dict(resolved)}


def render_simulation(results: Path, settings: Settings) -> str:
    s = simulate(results, settings)
    tool = f"{100 * s['tool_acc']:.1f}% (n={s['tool_n']})" if s["tool_acc"] is not None else "-"
    return (f"simulated {s['config']} over {results.name}: n={s['n']} "
            f"skill={100 * s['skill_acc']:.1f}% tool={tool} "
            f"routing $/case={s['routing_cost_case']:.6f} routing ms/case="
            f"{s['routing_ms_case']:.0f} resolved_by={s['resolved_by']}")
