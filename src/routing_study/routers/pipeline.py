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
When no consulted step accepts and one of them failed, the failure is surfaced as
`routing_error`, which the runner records as the row's error (excluded from accuracy) rather
than scoring the outage as an abstention. A failure a later step recovered from is kept in
`step_errors` only: the cascade did its job, the row is scored.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from routing_study.budget import BudgetExceededError
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
    # Study cost: ORIGINAL cost of each decision even when served from cache, so results do
    # not depend on cache warmth. `*billed_usd` is what this run actually paid (cached hits 0).
    cost_usd: float = 0.0  # consulted steps = what a production cascade pays
    shadow_cost_usd: float = 0.0  # every strategy that ran (= cost_usd outside shadow mode)
    billed_usd: float = 0.0
    shadow_billed_usd: float = 0.0
    latency_ms: float = 0.0  # sum of consulted pipeline steps (original latency if cached)
    routing_error: str | None = None  # no step accepted and a consulted step failed
    step_errors: list[str] = Field(default_factory=list)  # every consulted step's failure


def _accepts(step: PipelineStep, d: RouteDecision) -> bool:
    if d.choice is None:
        return False
    return step.min_confidence is None or d.confidence >= step.min_confidence


def _errors(decisions: list[RouteDecision]) -> list[str]:
    return [f"{d.strategy}: {d.usage['error']}" for d in decisions if d.usage.get("error")]


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
            s
            for s in dict.fromkeys([*(p.strategy for p in stage.pipeline), *extra])
            if s in routers
        ]

    @property
    def steps(self) -> list[PipelineStep]:
        return self.stage.pipeline[:1] if self.mode == "single" else self.stage.pipeline

    async def _safe_route(
        self, strategy: str, inp: RoutingInput, options: list[RouteOption], decider: _Decider
    ) -> RouteDecision:
        try:
            d = await self.routers[strategy].route(inp, options)
        except BudgetExceededError:
            raise  # a spend cap aborts the run, it is not a router failure
        except Exception as exc:  # recorded, never fatal
            d = RouteDecision(
                choice=None,
                confidence=0.0,
                strategy=strategy,
                usage={"error": f"{type(exc).__name__}: {exc}"[:500]},
            )
        decider.see(d)  # unblock later steps waiting in `decides` (errors, untraced runs)
        return d

    async def run(self, inp: RoutingInput, options: list[RouteOption]) -> PipelineResult:
        decider = _Decider(self.steps)
        token = DECIDES.set(decider.decides)
        try:
            return await self._run(inp, options, decider)
        finally:
            DECIDES.reset(token)

    async def _run(
        self, inp: RoutingInput, options: list[RouteOption], decider: _Decider
    ) -> PipelineResult:
        shadow: dict[str, RouteDecision] = {}
        if self.mode == "shadow":
            results = await asyncio.gather(
                *(self._safe_route(s, inp, options, decider) for s in self.shadow_strategies)
            )
            shadow = dict(zip(self.shadow_strategies, results, strict=True))

        consulted: list[RouteDecision] = []
        for i, step in enumerate(self.steps):
            d = shadow.get(step.strategy) or await self._safe_route(
                step.strategy, inp, options, decider
            )
            consulted.append(d)
            if _accepts(step, d):
                return self._result(d, step.strategy, i, consulted, shadow)
        last = consulted[-1]
        error = next(iter(_errors(consulted)), None)
        final = RouteDecision(
            choice=None,
            confidence=0.0,
            candidates=last.candidates,
            strategy=last.strategy,
            latency_ms=sum(c.latency_ms for c in consulted),
            cost_usd=sum(c.cost_usd for c in consulted),
            usage={"error": error} if error else {},
        )
        return self._result(final, None, None, consulted, shadow)

    def _result(
        self,
        decision: RouteDecision,
        resolved_by: str | None,
        step: int | None,
        consulted: list[RouteDecision],
        shadow: dict[str, RouteDecision],
    ) -> PipelineResult:
        ran = list(shadow.values()) if shadow else consulted
        return PipelineResult(
            decision=decision,
            resolved_by=resolved_by,
            cascade_step=step,
            abstained=resolved_by is None,
            mode=self.mode,
            steps=consulted,
            shadow=shadow,
            cost_usd=sum(d.cost_usd for d in consulted),
            shadow_cost_usd=sum(d.cost_usd for d in ran),
            billed_usd=sum(_spent(d) for d in consulted),
            shadow_billed_usd=sum(_spent(d) for d in ran),
            latency_ms=sum(d.latency_ms for d in consulted),
            routing_error=None if resolved_by else next(iter(_errors(consulted)), None),
            step_errors=_errors(consulted),
        )


def summary(dump: dict[str, Any] | None) -> dict[str, Any] | None:
    """Compact view of a `PipelineResult` dump: stage span metadata and result records."""
    if not dump:
        return None
    d = dump["decision"]
    keys = (
        "resolved_by",
        "cascade_step",
        "abstained",
        "mode",
        "cost_usd",
        "shadow_cost_usd",
        "billed_usd",
        "shadow_billed_usd",
        "latency_ms",
        "steps",
        "shadow",
        "routing_error",
        "step_errors",
    )
    return {
        "choice": d["choice"],
        "confidence": d["confidence"],
        "candidates": d["candidates"][:5],
        **{k: dump.get(k) for k in keys},
    }


# ---------------------------------------------------------------- factory


def build_routers(
    settings: Settings,
    strategies: set[str] | None = None,
    *,
    supported_parameters: dict[str, list[str]] | None = None,
) -> dict[str, Router]:
    """Instantiate the configured strategies (all, or only `strategies`)."""
    from routing_study.llm import EmbeddingsClient, chat_model_for
    from routing_study.routers.bm25 import BM25Router
    from routing_study.routers.embedding import EmbeddingRouter
    from routing_study.routers.hybrid import HybridRouter
    from routing_study.routers.jev import JevRouter
    from routing_study.routers.llm import LLMRouter
    from routing_study.routers.regex import RegexRouter
    from routing_study.settings import is_llm_strategy

    cfg = settings.strategies
    wanted = strategies if strategies is not None else set(cfg.configured())
    cache_dir = Path(settings.cache_dir)
    supported = supported_parameters or {}

    def _cache(enabled: bool) -> ResponseCache | None:
        return ResponseCache(str(cache_dir / "responses")) if enabled else None

    def _need(name: str) -> Any:
        c = cfg.get(name)
        if c is None:
            raise ValueError(f"strategy '{name}' used but not configured under `strategies`")
        return c

    out: dict[str, Router] = {}
    if "regex" in wanted:
        c = _need("regex")
        out["regex"] = RegexRouter.from_path(
            c.rules_path,
            dict(c.calibration),
            history_turns=c.history_turns,
            history_weight=c.history_weight,
        )
    if "bm25" in wanted or "hybrid" in wanted:
        c = cfg.bm25 or _need("bm25")
        bm25 = BM25Router(
            k1=c.k1,
            b=c.b,
            calibration=dict(c.calibration),
            stemmer=c.stemmer,
            prefix_len=c.prefix_len,
            stopwords=c.stopwords,
            field_repeats=c.field_repeats.model_dump(),
            history_turns=c.history_turns,
            history_weight=c.history_weight,
            variant=c.variant,
            delta=c.delta,
        )
        if "bm25" in wanted:
            out["bm25"] = bm25
    if "embedding" in wanted or "hybrid" in wanted:
        c = _need("embedding")
        emb = EmbeddingRouter(
            EmbeddingsClient.for_config(settings, c),
            vector_cache_dir=str(cache_dir / "embeddings"),
            similarity=c.similarity,
            confidence=c.confidence,
            softmax_temperature=c.softmax_temperature,
            margin_scale=c.margin_scale,
            cache=_cache(c.cache),
        )
        if "embedding" in wanted:
            out["embedding"] = emb
    if "hybrid" in wanted:
        out["hybrid"] = HybridRouter(bm25, emb, rrf_k=_need("hybrid").rrf_k)
    for name in sorted(n for n in wanted if is_llm_strategy(n)):  # one LLMRouter per LLM
        c = _need(name)
        out[name] = LLMRouter(
            chat_model_for(settings, c, supported_parameters=supported.get(c.model)),
            settings,
            model=c.model,
            history_turns=c.history_turns,
            allow_abstain=c.allow_abstain,
            cache=_cache(c.cache),
            name=name,
            confidence=c.confidence,
        )
    if "jev" in wanted:
        c = _need("jev")
        # jev-router lists no supported parameters: default [] drops temperature/seed
        chat = chat_model_for(settings, c, supported_parameters=supported.get(c.model, []))
        out["jev"] = JevRouter(
            chat,
            settings,
            model=c.model,
            parse_retries=c.parse_retries,
            history_turns=c.history_turns,
            allow_abstain=c.allow_abstain,
            cache=_cache(c.cache),
        )
    return out


def local_models(settings: Settings, names: list[str]) -> set[str]:
    """Distinct Ollama models the given strategies load (hybrid loads the embedder)."""
    cfg = settings.strategies
    out: set[str] = set()
    for n in names:
        c = cfg.get("embedding" if n == "hybrid" else n)
        if c is not None and getattr(c, "provider", None) == "ollama":
            out.add(c.model)
    return out


def shadow_set(settings: Settings) -> list[str]:
    """Strategies a shadow pass runs besides the pipeline steps: `routing.shadow_strategies`
    when given, else every configured strategy — minus the local (Ollama) LLM routers when the
    local models of the pass exceed `ollama_max_loaded_models`: with one model resident at a
    time, parallel shadow calls would swap models per request and the load time would pollute
    their latency. Those routers are measured by their own routing-only runs instead."""
    r, cfg = settings.routing, settings.strategies
    if r.shadow_strategies:
        return list(r.shadow_strategies)
    names = cfg.configured()
    if len(local_models(settings, names)) <= settings.ollama_max_loaded_models:
        return names
    local_llms = {n for n, c in cfg.llm_strategies().items() if c.provider == "ollama"} - {
        st.strategy for stage in (r.skill, r.tool) for st in stage.pipeline
    }
    return [n for n in names if n not in local_llms]


def build_pipeline(
    settings: Settings, level: Literal["skill", "tool"], routers: dict[str, Router]
) -> RoutingPipeline:
    mode = settings.routing.mode
    if mode == "native":
        raise ValueError("routing.mode=native has no routing pipeline")
    stage = settings.routing.skill if level == "skill" else settings.routing.tool
    return RoutingPipeline(stage, routers, mode=mode, shadow_strategies=shadow_set(settings))
