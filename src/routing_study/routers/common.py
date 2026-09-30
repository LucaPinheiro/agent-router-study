"""Shared router plumbing: timing, response cache, Langfuse spans, text normalization."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any, ClassVar

import diskcache
from langfuse import get_client, observe

from routing_study.prompts import escape_data
from routing_study.routers.base import RouteDecision, RouteOption, RoutingInput

log = logging.getLogger(__name__)

# Set by `RoutingPipeline.run` (copied into gather() tasks): resolves whether a decision is the
# one the pipeline acts on, so the router span gets `decisive` / `shadow` while still open.
DECIDES: ContextVar[Callable[[RouteDecision], Awaitable[bool]] | None] = ContextVar(
    "DECIDES", default=None
)
# Set by the runner per (case, repetition): part of the response-cache key, so `--reps` are
# independent samples while re-running the same repetition stays free.
REPETITION: ContextVar[int] = ContextVar("REPETITION", default=1)


# ---------------------------------------------------------------- text


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Lowercase + strip accents (pt-BR friendly)."""
    return strip_accents(text.lower())


_PT_STOPWORDS = frozenset(
    """a o as os um uma uns umas de da do das dos em no na nos nas por para pra pro com sem
    e ou que se me mim meu minha meus minhas eu voce vc ele ela isso isto esse essa este esta
    ja nao sim foi ser ter tem tenho esta estou e ao aos la lo quero queria gostaria preciso
    como qual quais quando onde porque pois mais muito pelo pela ate sobre entre ainda so""".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"\w+", normalize(text)) if t not in _PT_STOPWORDS]


def option_document(opt: RouteOption) -> str:
    return " ".join([opt.description, *opt.examples, *opt.keywords])


def history_text(inp: RoutingInput, turns: int) -> str:
    if turns <= 0 or not inp.history:
        return ""
    return "\n".join(f"{m.role}: {escape_data(m.content)}" for m in inp.history[-turns:])


# ---------------------------------------------------------------- cache


def cache_key(
    strategy: str,
    params: dict[str, Any],
    inp: RoutingInput,
    options: list[RouteOption],
    namespace: str = "",
    rep: int = 1,
) -> str:
    """`params`: everything besides the input that shapes the decision (model, router and
    sampling config, rendered prompt/schema) — see `BaseRouter.cache_params`."""
    payload = {
        "strategy": strategy,
        "params": params,
        "ns": namespace,
        "rep": rep,
        "input": inp.model_dump(mode="json"),
        "options": [o.model_dump(mode="json") for o in options],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class StrictJSONDisk(diskcache.JSONDisk):
    """JSONDisk that refuses pickle rows. `JSONDisk` still falls back to `pickle.load` for a
    row stored in pickle mode (or a non-raw key), so a planted row in the cache DB would run
    code; here it raises instead (security review)."""

    def get(self, key: Any, raw: bool) -> Any:
        if not raw:
            raise ValueError("refusing a pickled cache key")
        return super().get(key, raw)

    def fetch(self, mode: int, filename: Any, value: Any, read: bool) -> Any:
        if mode == diskcache.core.MODE_PICKLE:
            raise ValueError("refusing a pickled cache value")
        return super().fetch(mode, filename, value, read)


class ResponseCache:
    """Disk cache of router decisions. Hits keep the ORIGINAL latency/cost, with cached=True.

    `namespace` is an extra key prefix; repetitions are keyed via `REPETITION`.
    """

    def __init__(self, directory: str, namespace: str = "") -> None:
        self._cache = diskcache.Cache(directory, disk=StrictJSONDisk)  # never unpickles
        self.namespace = namespace

    def get(self, key: str) -> RouteDecision | None:
        raw = self._cache.get(key)
        if raw is None:
            return None
        return RouteDecision.model_validate(raw).model_copy(update={"cached": True})

    def set(self, key: str, decision: RouteDecision) -> None:
        self._cache.set(key, decision.model_dump(mode="json"))

    def close(self) -> None:
        self._cache.close()


# ---------------------------------------------------------------- tracing (no-op safe)


def tracing_active() -> bool:
    """True when a Langfuse client exists or can be built from env; else skip `observe`.

    Avoids the SDK's per-call "initialized without public_key" / "no active span" warnings
    when Langfuse is not configured (unit tests, offline runs).
    """
    if os.environ.get("LANGFUSE_TRACING_ENABLED", "true").lower() == "false":
        return False
    if os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return True
    try:  # a client initialized explicitly (e.g. Langfuse(public_key=...)) in this process
        from langfuse._client.resource_manager import LangfuseResourceManager

        return bool(LangfuseResourceManager._instances)
    except Exception:
        return False


async def _annotate(
    inp: RoutingInput, decision: RouteDecision, *, generation: bool, model: str | None
) -> None:
    decides = DECIDES.get()
    decisive = bool(decides and await decides(decision))
    name = f"route.{inp.level}.{decision.strategy}"
    metadata = {
        "choice": decision.choice,
        "confidence": decision.confidence,
        "candidates": decision.candidates[:5],
        "cached": decision.cached,
        "latency_ms": decision.latency_ms,
        "cost_usd": decision.cost_usd,
        "level": inp.level,
        "loaded_skill": inp.loaded_skill,
        "decisive": decisive,
        "shadow": not decisive,
        **{
            k: v
            for k, v in decision.usage.items()
            if k in ("served_model", "provider", "parse_fail", "error", "queue_ms", "retry_ms")
        },
    }
    try:
        client = get_client()
        if generation:
            usage = decision.usage
            client.update_current_generation(
                name=name,
                model=usage.get("served_model") or model,
                metadata=metadata,
                output={"choice": decision.choice, "confidence": decision.confidence},
                usage_details={
                    "input": int(usage.get("prompt_tokens") or 0),
                    "output": int(usage.get("completion_tokens") or 0),
                },
                # cached hits cost nothing now; the original cost stays in metadata
                cost_details={"total": 0.0 if decision.cached else decision.cost_usd},
            )
        else:
            client.update_current_span(
                name=name,
                metadata=metadata,
                output={"choice": decision.choice, "confidence": decision.confidence},
            )
    except Exception:  # tracing must never break routing
        log.debug("langfuse annotate failed", exc_info=True)


# ---------------------------------------------------------------- base router


class BaseRouter:
    """Template: cache lookup -> `_decide` -> latency fill -> cache store -> span annotate."""

    name: ClassVar[str]
    paid: ClassVar[bool] = False  # paid routers become Langfuse generations

    def __init__(self, cache: ResponseCache | None = None) -> None:
        self.cache = cache

    @property
    def model(self) -> str | None:
        return None

    async def _decide(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        raise NotImplementedError

    def cache_params(self, inp: RoutingInput, options: list[RouteOption]) -> dict[str, Any]:
        """Config + prompt that shape the decision; routers with a cache extend it."""
        return {"model": self.model}

    async def route(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        if not tracing_active():
            return await self._route(inp, options)
        if self.paid:
            return await self._route_generation(inp, options)
        return await self._route_span(inp, options)

    @observe(name="route", as_type="span", capture_input=False, capture_output=False)
    async def _route_span(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        decision = await self._route(inp, options)
        await _annotate(inp, decision, generation=False, model=self.model)
        return decision

    @observe(name="route", as_type="generation", capture_input=False, capture_output=False)
    async def _route_generation(
        self, inp: RoutingInput, options: list[RouteOption]
    ) -> RouteDecision:
        decision = await self._route(inp, options)
        await _annotate(inp, decision, generation=True, model=self.model)
        return decision

    async def _route(self, inp: RoutingInput, options: list[RouteOption]) -> RouteDecision:
        key = None
        if self.cache is not None:
            key = cache_key(
                self.name,
                self.cache_params(inp, options),
                inp,
                options,
                self.cache.namespace,
                REPETITION.get(),
            )
            hit = self.cache.get(key)
            if hit is not None:
                return hit
        t0 = time.perf_counter()
        decision = await self._decide(inp, options)
        # Routing latency: HTTP work + local compute, not semaphore/RPM queueing or retry
        # backoff (reported separately in usage.queue_ms / usage.retry_ms).
        waited = float(decision.usage.get("queue_ms") or 0) + float(
            decision.usage.get("retry_ms") or 0
        )
        latency = max(0.0, (time.perf_counter() - t0) * 1000 - waited)
        if decision.latency_ms > 0:  # set by a composite router from its sub-decisions
            latency = decision.latency_ms
        decision = decision.model_copy(update={"latency_ms": latency, "strategy": self.name})
        # never cache failures: a transient parse failure / error must be retried next time
        if (
            self.cache is not None
            and key is not None
            and not decision.usage.get("error")
            and not decision.usage.get("parse_fail")
        ):
            self.cache.set(key, decision)
        return decision


def abstain(strategy: str, **usage: Any) -> RouteDecision:
    return RouteDecision(choice=None, confidence=0.0, strategy=strategy, usage=usage)


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))
