"""RoutingPipeline single / cascade / shadow logic with scripted routers."""

from __future__ import annotations

import asyncio

import pytest
from router_helpers import skill_input

from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput
from routing_study.routers.common import DECIDES
from routing_study.routers.pipeline import RoutingPipeline, build_pipeline, build_routers
from routing_study.settings import PipelineStep, StageConfig, load_settings


class Scripted:
    def __init__(
        self,
        name: str,
        choice: str | None,
        conf: float,
        cost: float = 0.0,
        cached: bool = False,
        delay: float = 0.0,
        fail: bool = False,
    ) -> None:
        self.name, self.choice, self.conf, self.cost = name, choice, conf, cost
        self.cached, self.delay, self.fail = cached, delay, fail
        self.calls = 0
        self.started: float | None = None
        self.decisive: bool | None = None

    async def route(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        self.calls += 1
        self.started = asyncio.get_running_loop().time()
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("boom")
        d = RouteDecision(
            choice=self.choice,
            confidence=self.conf,
            strategy=self.name,
            cost_usd=self.cost,
            latency_ms=10.0,
            cached=self.cached,
        )
        decides = DECIDES.get()  # what a router span does before it closes
        self.decisive = bool(decides and await decides(d))
        return d


def stage(*steps: tuple[str, float | None]) -> StageConfig:
    return StageConfig(pipeline=[PipelineStep(strategy=s, min_confidence=m) for s, m in steps])


INP = skill_input("x")


async def test_cascade_first_confident_step_decides(skill_options):
    r = {
        "regex": Scripted("regex", "a", 0.5),
        "jev": Scripted("jev", "b", 0.8, cost=0.01),
        "llm": Scripted("llm", "c", 0.9, cost=0.1),
    }
    p = RoutingPipeline(stage(("regex", 0.9), ("jev", 0.75), ("llm", None)), r)
    res = await p.run(INP, skill_options)
    assert res.decision.choice == "b" and res.resolved_by == "jev" and res.cascade_step == 1
    assert r["llm"].calls == 0
    assert res.cost_usd == pytest.approx(0.01) and res.latency_ms == pytest.approx(20.0)
    assert [s.strategy for s in res.steps] == ["regex", "jev"]


async def test_cascade_last_step_accepts_always(skill_options):
    r = {"regex": Scripted("regex", None, 0.0), "llm": Scripted("llm", "c", 0.1)}
    res = await RoutingPipeline(stage(("regex", 0.9), ("llm", None)), r).run(INP, skill_options)
    assert res.decision.choice == "c" and res.resolved_by == "llm" and res.cascade_step == 1


async def test_cascade_last_step_with_threshold_can_abstain(skill_options):
    r = {"regex": Scripted("regex", "a", 0.5), "llm": Scripted("llm", "c", 0.1)}
    res = await RoutingPipeline(stage(("regex", 0.9), ("llm", 0.5)), r).run(INP, skill_options)
    assert res.abstained and res.decision.choice is None and res.resolved_by is None
    assert res.cascade_step is None and len(res.steps) == 2


async def test_abstaining_router_never_accepted_even_without_threshold(skill_options):
    r = {"llm": Scripted("llm", None, 0.0)}
    res = await RoutingPipeline(stage(("llm", None)), r, mode="single").run(INP, skill_options)
    assert res.abstained


async def test_single_uses_only_first_step(skill_options):
    r = {"regex": Scripted("regex", "a", 0.2), "llm": Scripted("llm", "c", 0.9)}
    p = RoutingPipeline(stage(("regex", 0.5), ("llm", None)), r, mode="single")
    res = await p.run(INP, skill_options)
    assert res.abstained and r["llm"].calls == 0


async def test_shadow_runs_all_in_parallel_and_decider_follows_pipeline(skill_options):
    r = {
        "regex": Scripted("regex", "a", 0.95, delay=0.05),
        "bm25": Scripted("bm25", "b", 0.9, delay=0.05),
        "llm": Scripted("llm", "c", 0.9, cost=0.1, delay=0.05),
    }
    p = RoutingPipeline(stage(("regex", 0.9), ("llm", None)), r, mode="shadow")
    t0 = asyncio.get_running_loop().time()
    res = await p.run(INP, skill_options)
    elapsed = asyncio.get_running_loop().time() - t0
    assert elapsed < 0.12  # parallel, not 3 x 0.05
    assert set(res.shadow) == {"regex", "bm25", "llm"}
    assert all(x.calls == 1 for x in r.values())  # nothing re-run by the cascade
    assert res.decision.choice == "a" and res.resolved_by == "regex" and res.cascade_step == 0
    assert res.cost_usd == 0.0  # the cascade stopped at regex: production pays nothing
    assert res.shadow_cost_usd == pytest.approx(0.1)  # shadow spend is reported apart
    assert res.shadow["llm"].choice == "c"


@pytest.mark.parametrize("mode", ["cascade", "shadow"])
async def test_only_the_deciding_strategy_is_decisive(skill_options, mode):
    # regex is below threshold and slower than jev: jev must still wait for it, not self-elect
    r = {
        "regex": Scripted("regex", "a", 0.5, delay=0.03),
        "jev": Scripted("jev", "b", 0.8),
        "llm": Scripted("llm", "c", 0.9),
        "bm25": Scripted("bm25", "d", 0.99),
    }
    p = RoutingPipeline(stage(("regex", 0.9), ("jev", 0.75), ("llm", None)), r, mode=mode)
    res = await p.run(INP, skill_options)
    assert res.resolved_by == "jev"
    ran = {k: v.decisive for k, v in r.items() if v.calls}
    assert ran == (
        {"regex": False, "jev": True}
        if mode == "cascade"
        else {"regex": False, "jev": True, "llm": False, "bm25": False}
    )


async def test_shadow_restricted_to_configured_extra_strategies(skill_options):
    r = {
        "regex": Scripted("regex", "a", 0.95),
        "bm25": Scripted("bm25", "b", 0.9),
        "llm": Scripted("llm", "c", 0.9),
    }
    p = RoutingPipeline(stage(("regex", 0.9)), r, mode="shadow", shadow_strategies=["llm"])
    res = await p.run(INP, skill_options)
    assert set(res.shadow) == {"regex", "llm"} and r["bm25"].calls == 0


async def test_router_error_becomes_abstention_and_cascade_continues(skill_options):
    r = {"jev": Scripted("jev", "a", 0.9, fail=True), "llm": Scripted("llm", "c", 0.8)}
    res = await RoutingPipeline(stage(("jev", 0.7), ("llm", None)), r).run(INP, skill_options)
    assert res.resolved_by == "llm"
    assert "RuntimeError: boom" in res.steps[0].usage["error"]


async def test_cost_is_original_cost_and_billed_is_what_was_paid(skill_options):
    """B6: cost_usd (study cost) must not depend on cache warmth; billed_usd does."""
    r = {"llm": Scripted("llm", "c", 0.9, cost=0.5, cached=True)}
    res = await RoutingPipeline(stage(("llm", None)), r).run(INP, skill_options)
    assert res.decision.cost_usd == 0.5 and res.decision.cached  # original cost kept
    assert res.cost_usd == 0.5 and res.billed_usd == 0.0

    r = {
        "regex": Scripted("regex", "a", 0.95),
        "llm": Scripted("llm", "c", 0.8, cost=0.2, cached=True),
    }
    res = await RoutingPipeline(stage(("regex", None)), r, mode="shadow").run(INP, skill_options)
    assert res.shadow_cost_usd == 0.2 and res.shadow_billed_usd == 0.0


def test_pipeline_validates_strategies():
    with pytest.raises(ValueError, match="no router"):
        RoutingPipeline(stage(("jev", None)), {})
    with pytest.raises(ValueError, match="empty"):
        RoutingPipeline(StageConfig(), {})


def test_build_from_experiment_yaml(tmp_path):
    s = load_settings(
        "config/experiments/e9_regex_jev_llm.yaml", cache_dir=str(tmp_path), openrouter_api_key="k"
    )
    routers = build_routers(
        s, {"regex", "jev", "llm"}, supported_parameters={"typesafe/jev-router": []}
    )
    skill = build_pipeline(s, "skill", routers)
    tool = build_pipeline(s, "tool", routers)
    assert [x.strategy for x in skill.steps] == ["regex", "jev", "llm"]
    assert [x.min_confidence for x in skill.steps] == [0.9, 0.75, None]
    assert [x.strategy for x in tool.steps] == ["jev", "llm"]
    assert s.routing.tool.expose_top_k == 2
    e0 = load_settings("config/experiments/e0_native.yaml", openrouter_api_key="k")
    with pytest.raises(ValueError, match="native"):
        build_pipeline(e0, "skill", {})


async def test_router_error_is_a_routing_error_not_an_abstention(skill_options):
    """B3: an outage must not score as a correct abstention."""
    from routing_study.routers.pipeline import summary

    r = {"llm": Scripted("llm", "c", 0.9, fail=True)}
    res = await RoutingPipeline(stage(("llm", None)), r).run(INP, skill_options)
    assert res.abstained and res.routing_error and "RuntimeError: boom" in res.routing_error
    assert res.decision.usage["error"] == res.routing_error
    assert summary(res.model_dump(mode="json"))["routing_error"] == res.routing_error

    # code finding 2: a later step that accepts recovers the failure: not a row error, the
    # recovered failure is kept in step_errors
    r = {"jev": Scripted("jev", "a", 0.9, fail=True), "llm": Scripted("llm", "c", 0.8)}
    res = await RoutingPipeline(stage(("jev", 0.7), ("llm", None)), r).run(INP, skill_options)
    assert res.resolved_by == "llm" and res.routing_error is None
    assert len(res.step_errors) == 1 and "jev: RuntimeError: boom" in res.step_errors[0]
    assert summary(res.model_dump(mode="json"))["step_errors"] == res.step_errors

    # a failing shadow-only strategy does not affect the decision
    r = {"regex": Scripted("regex", "a", 0.95), "llm": Scripted("llm", "c", 0.8, fail=True)}
    res = await RoutingPipeline(stage(("regex", None)), r, mode="shadow").run(INP, skill_options)
    assert res.routing_error is None and "error" in res.shadow["llm"].usage
