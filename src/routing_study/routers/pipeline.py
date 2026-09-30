"""RoutingPipeline: single | cascade | shadow over any `Router`s, per stage (skill or tool).

- single:  only pipeline[0]; accepted if it chose and passes its min_confidence (if any).
- cascade: first step whose confidence >= min_confidence decides; a step without
           min_confidence (typically the last) accepts any non-abstaining choice.
- shadow:  every strategy (pipeline + `shadow_strategies`, default all routers) runs in parallel via
           asyncio.gather; the decision follows the pipeline's rules over those results,
           the rest is only logged.
Router spans are tagged while they are open: `decisive=true` on the strategy the pipeline acts
on, `shadow=true` on every other one (plan §6.2); see `DECIDES`.
A router exception becomes an abstaining decision with usage["error"] so a batch never dies.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from routing_study.routers.base import RouteDecision, RouteOption, Router, RoutingInput
from routing_study.routers.common import DECIDES, ResponseCache
from routing_study.settings import PipelineStep, Settings, StageConfig

Mode = Literal["single", "cascade", "shadow"]


class PipelineResult(BaseModel):
    decision: RouteDecision  # final decision (choice=None when abstained)
    resolved_by: str | None = None  # strategy that decided
    cascade_step: int | None = None  # 0-based index in the pipeline
    abstained: bool = False
    mode: Mode
    steps: list[RouteDecision] = Field(default_factory=list)  # pipeline steps consulted
    shadow: dict[str, RouteDecision] = Field(default_factory=dict)  # all shadow decisions
    cost_usd: float = 0.0  # consulted steps = what a production cascade pays (cached hits 0)
    shadow_cost_usd: float = 0.0  # every strategy that ran (= cost_usd outside shadow mode)
    latency_ms: float = 0.0  # sum of consulted pipeline steps (original latency if cached)


def _accepts(step: PipelineStep, d: RouteDecision) -> bool:
    if d.choice is None:
        return False
    return step.min_confidence is None or d.confidence >= step.min_confidence


def _spent(d: RouteDecision) -> float:
    return 0.0 if d.cached else d.cost_usd


class _Decider:
    """Per-run: which decision the pipeline acts on (first accepting step, in order)."""

    def __init__(self, steps: list[PipelineStep]) -> None:
        self.steps = steps
        loop = asyncio.get_running_loop()
        self.seen = {s.strategy: loop.create_future() for s in steps}

    def see(self, d: RouteDecision) -> None:
        fut = self.seen.get(d.strategy)
        if fut is not None and not fut.done():
            fut.set_result(d)

    async def decides(self, d: RouteDecision) -> bool:
        """Waits only for EARLIER steps, so shadow tasks can call it inside their open span."""
        if d.strategy not in self.seen:  # not a pipeline step: shadow only
            return False
        self.see(d)
        for step in self.steps:
            if step.strategy == d.strategy:
                return _accepts(step, d)
            if _accepts(step, await self.seen[step.strategy]):
                return False
        return False


class RoutingPipeline:
    def __init__(
        self,
        stage: StageConfig,
        routers: dict[str, Router],
        *,
        mode: Mode = "cascade",
        shadow_strategies: list[str] | None = None,
    ) -> None:
        if not stage.pipeline:
            raise ValueError("routing pipeline is empty")
        missing = {s.strategy for s in stage.pipeline} - routers.keys()
        if missing:
            raise ValueError(f"no router configured for strategies: {sorted(missing)}")
        self.stage = stage
        self.routers = routers
        self.mode = mode
        # Shadow runs the pipeline strategies + `shadow_strategies` (default: every router).
        extra = list(shadow_strategies) if shadow_strategies else list(routers)
        self.shadow_strategies = [
            s for s in dict.fromkeys([*(p.strategy for p in stage.pipeline), *extra])
            if s in routers
        ]

    @property
    def steps(self) -> list[PipelineStep]:
        return self.stage.pipeline[:1] if self.mode == "single" else self.stage.pipeline

    async def _safe_route(self, strategy: str, inp: RoutingInput, options: list[RouteOption],
                          decider: _Decider) -> RouteDecision:
        try:
            d = await self.routers[strategy].route(inp, options)
        except Exception as exc:  # recorded, never fatal
            d = RouteDecision(choice=None, confidence=0.0, strategy=strategy,
                              usage={"error": f"{type(exc).__name__}: {exc}"[:500]})
        decider.see(d)  # unblock later steps waiting in `decides` (errors, untraced runs)
        return d

    async def run(self, inp: RoutingInput, options: list[RouteOption]) -> PipelineResult:
        decider = _Decider(self.steps)
        token = DECIDES.set(decider.decides)
        try:
            return await self._run(inp, options, decider)
        finally:
            DECIDES.reset(token)

    async def _run(self, inp: RoutingInput, options: list[RouteOption],
                   decider: _Decider) -> PipelineResult:
        shadow: dict[str, RouteDecision] = {}
        if self.mode == "shadow":
            results = await asyncio.gather(
                *(self._safe_route(s, inp, options, decider) for s in self.shadow_strategies)
            )
            shadow = dict(zip(self.shadow_strategies, results, strict=True))

        consulted: list[RouteDecision] = []
        for i, step in enumerate(self.steps):
            d = shadow.get(step.strategy) or await self._safe_route(step.strategy, inp, options,
                                                                      decider)
            consulted.append(d)
            if _accepts(step, d):
                return self._result(d, step.strategy, i, consulted, shadow)
        last = consulted[-1]
        final = RouteDecision(
            choice=None,
            confidence=0.0,
            candidates=last.candidates,
            strategy=last.strategy,
            latency_ms=sum(c.latency_ms for c in consulted),
            cost_usd=sum(c.cost_usd for c in consulted),
        )
        return self._result(final, None, None, consulted, shadow)

    def _result(self, decision: RouteDecision, resolved_by: str | None, step: int | None,
                consulted: list[RouteDecision],
                shadow: dict[str, RouteDecision]) -> PipelineResult:
        return PipelineResult(
            decision=decision,
            resolved_by=resolved_by,
            cascade_step=step,
            abstained=resolved_by is None,
            mode=self.mode,
            steps=consulted,
            shadow=shadow,
            cost_usd=sum(_spent(d) for d in consulted),
            shadow_cost_usd=sum(_spent(d) for d in (shadow.values() if shadow else consulted)),
            latency_ms=sum(d.latency_ms for d in consulted),
        )


def summary(dump: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compact view of a `PipelineResult` dump: stage span metadata and result records."""
    if not dump:
        return None
    d = dump["decision"]
    keys = ("resolved_by", "cascade_step", "abstained", "mode", "cost_usd", "shadow_cost_usd",
            "latency_ms", "steps", "shadow")
    return {"choice": d["choice"], "confidence": d["confidence"],
            "candidates": d["candidates"][:5], **{k: dump[k] for k in keys}}


# ---------------------------------------------------------------- factory


def build_routers(settings: Settings, strategies: set[str] | None = None,
                  *, cache_namespace: str = "",
                  supported_parameters: dict[str, list[str]] | None = None,
                  ) -> dict[str, Router]:
    """Instantiate the configured strategies (all, or only `strategies`)."""
    from routing_study.llm import EmbeddingsClient, make_chat_model
    from routing_study.routers.bm25 import BM25Router
    from routing_study.routers.embedding import EmbeddingRouter
    from routing_study.routers.hybrid import HybridRouter
    from routing_study.routers.jev import JevRouter
    from routing_study.routers.llm import LLMRouter
    from routing_study.routers.regex import RegexRouter

    cfg = settings.strategies
    wanted = strategies if strategies is not None else {
        n for n in ("regex", "bm25", "embedding", "llm", "jev", "hybrid") if getattr(cfg, n)
    }
    cache_dir = Path(settings.cache_dir)
    supported = supported_parameters or {}

    def _cache(enabled: bool) -> ResponseCache | None:
        return ResponseCache(str(cache_dir / "responses"), cache_namespace) if enabled else None

    def _need(name: str) -> Any:
        c = getattr(cfg, name)
        if c is None:
            raise ValueError(f"strategy '{name}' used but not configured under `strategies`")
        return c

    out: dict[str, Router] = {}
    if "regex" in wanted:
        out["regex"] = RegexRouter.from_path(_need("regex").rules_path)
    if "bm25" in wanted or "hybrid" in wanted:
        c = cfg.bm25 or _need("bm25")
        bm25 = BM25Router(k1=c.k1, b=c.b)
        if "bm25" in wanted:
            out["bm25"] = bm25
    if "embedding" in wanted or "hybrid" in wanted:
        c = _need("embedding")
        emb = EmbeddingRouter(
            EmbeddingsClient(settings, c.model, provider=c.provider),
            vector_cache_dir=str(cache_dir / "embeddings"),
            similarity=c.similarity, confidence=c.confidence,
            softmax_temperature=c.softmax_temperature, margin_scale=c.margin_scale,
            cache=_cache(c.cache),
        )
        if "embedding" in wanted:
            out["embedding"] = emb
    if "hybrid" in wanted:
        out["hybrid"] = HybridRouter(bm25, emb, rrf_k=_need("hybrid").rrf_k)
    if "llm" in wanted:
        c = _need("llm")
        chat = make_chat_model(settings, c.model, temperature=c.temperature, seed=c.seed,
                               provider=c.provider, max_tokens=256,
                               supported_parameters=supported.get(c.model))
        out["llm"] = LLMRouter(chat, settings, model=c.model, history_turns=c.history_turns,
                               allow_abstain=c.allow_abstain, cache=_cache(c.cache))
    if "jev" in wanted:
        c = _need("jev")
        chat = make_chat_model(settings, c.model, provider=c.provider,
                               supported_parameters=supported.get(c.model, []))
        out["jev"] = JevRouter(chat, settings, model=c.model, parse_retries=c.parse_retries,
                               history_turns=c.history_turns, allow_abstain=c.allow_abstain,
                               cache=_cache(c.cache))
    return out


def build_pipeline(settings: Settings, level: Literal["skill", "tool"],
                   routers: dict[str, Router]) -> RoutingPipeline:
    mode = settings.routing.mode
    if mode == "native":
        raise ValueError("routing.mode=native has no routing pipeline")
    stage = settings.routing.skill if level == "skill" else settings.routing.tool
    return RoutingPipeline(stage, routers, mode=mode,
                           shadow_strategies=list(settings.routing.shadow_strategies))
