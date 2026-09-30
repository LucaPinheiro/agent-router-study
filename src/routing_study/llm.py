"""OpenRouter clients: chat (LangChain ChatOpenAI), embeddings (/embeddings), slug validation.

- Cost comes from OpenRouter's `usage.cost` (`usage: {include: true}`); never estimated locally.
- The served model and provider are read from the response, not from config.
- Retries: tenacity with exponential backoff; concurrency: one asyncio semaphore per provider.
"""

from __future__ import annotations

import asyncio
import time
import weakref
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx
import httpx2
import numpy as np
import openai
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from routing_study.settings import ProviderPrefs, ReasoningPrefs, Settings


class UnknownModelError(RuntimeError):
    pass


class OpenRouterChat(ChatOpenAI):
    """ChatOpenAI that keeps OpenRouter's top-level `provider` in `response_metadata`."""

    def _create_chat_result(
        self, response: dict | openai.BaseModel, generation_info: dict | None = None
    ) -> ChatResult:
        error = (
            response.get("error")
            if isinstance(response, dict)
            else getattr(response, "error", None)
        )
        if error:  # HTTP 200 with an error body (B8): retried by code, like an HTTP status
            raise OpenRouterBodyError({"error": error})
        result = super()._create_chat_result(response, generation_info)
        provider = (
            response.get("provider")
            if isinstance(response, dict)
            else getattr(response, "provider", None)
        )
        if result.llm_output is not None and provider:
            result.llm_output["provider"] = provider
        for gen in result.generations:
            if isinstance(gen.message, AIMessage) and provider:
                gen.message.response_metadata["provider"] = provider
        return result


def provider_extra_body(
    prefs: ProviderPrefs | None, reasoning: ReasoningPrefs | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"usage": {"include": True}}
    if reasoning is not None:
        body["reasoning"] = reasoning.model_dump(exclude_none=True)
    if prefs is not None and (prefs.order or not prefs.allow_fallbacks):
        provider: dict[str, Any] = {"allow_fallbacks": prefs.allow_fallbacks}
        if prefs.order:
            provider["order"] = list(prefs.order)
        body["provider"] = provider
    return body


class _LoopLocalTransport(httpx2.AsyncBaseTransport):
    """One connection pool per event loop. A pooled keep-alive connection belongs to the loop
    that opened it; langchain_openai shares ONE cached default client per process, so a call
    after an earlier `asyncio.run(...)` reused a dead loop's connection ("Event loop is
    closed"). Pools of closed loops are dropped (their sockets died with the loop)."""

    def __init__(self) -> None:
        self._pools: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, httpx2.AsyncHTTPTransport
        ] = weakref.WeakKeyDictionary()

    def _pool(self) -> httpx2.AsyncHTTPTransport:
        loop = asyncio.get_running_loop()
        for dead in [lp for lp in self._pools if lp.is_closed()]:
            del self._pools[dead]
        pool = self._pools.get(loop)
        if pool is None:  # openai's DefaultAsyncHttpxClient connection limits
            pool = self._pools[loop] = httpx2.AsyncHTTPTransport(
                limits=httpx2.Limits(max_connections=1000, max_keepalive_connections=100)
            )
        return pool

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        return await self._pool().handle_async_request(request)

    async def aclose(self) -> None:
        pool = self._pools.pop(asyncio.get_running_loop(), None)
        if pool is not None:
            await pool.aclose()


# shared by every chat model (like langchain_openai's cached default), but loop-safe
_CHAT_HTTP_CLIENT = openai.DefaultAsyncHttpxClient(transport=_LoopLocalTransport())


def make_chat_model(
    settings: Settings,
    model: str,
    *,
    temperature: float | None = None,
    seed: int | None = None,
    provider: ProviderPrefs | None = None,
    reasoning: ReasoningPrefs | None = None,
    max_tokens: int | None = None,
    supported_parameters: Iterable[str] | None = None,
    http_async_client: Any | None = None,
) -> OpenRouterChat:
    """ChatOpenAI against OpenRouter. Retries are owned by `call_with_retry`, not the SDK.

    `supported_parameters` (from `validate_models`) drops params the model does not accept;
    `None` means "unknown" and sends what was asked. `http_async_client` lets tests inject a
    plain `httpx.AsyncClient` (openai>=3 defaults to `httpx2`, which respx cannot mock); the
    default is a client with one connection pool per event loop (`_LoopLocalTransport`).
    """
    params: dict[str, Any] = {"temperature": temperature, "seed": seed}
    if supported_parameters is not None:
        supported = set(supported_parameters)
        params = {k: (v if k in supported else None) for k, v in params.items()}
        # finding 6: `reasoning` only goes to models that list it; asking a model that
        # cannot reason to reason is a config error, not something to drop silently
        if reasoning is not None and "reasoning" not in supported:
            if reasoning.enabled:
                raise ValueError(f"{model} does not support reasoning (supported_parameters)")
            reasoning = None
    kwargs: dict[str, Any] = {
        "model": model,
        "base_url": settings.openrouter_base_url,
        "api_key": settings.openrouter_api_key.get_secret_value() or "missing",
        "extra_body": provider_extra_body(provider, reasoning),
        "max_retries": 0,
        "timeout": settings.request_timeout_s,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    kwargs["http_async_client"] = (
        _CHAT_HTTP_CLIENT if http_async_client is None else http_async_client
    )
    kwargs.update({k: v for k, v in params.items() if v is not None})
    return OpenRouterChat(**kwargs)


def extract_call_usage(msg: AIMessage | None) -> dict[str, Any]:
    """Cost (USD), tokens, served model and provider from one OpenRouter chat response."""
    if msg is None:
        return {"cost_usd": 0.0}
    meta = msg.response_metadata or {}
    token_usage = meta.get("token_usage") or {}
    cost = token_usage.get("cost")
    return {
        "cost_usd": float(cost) if cost is not None else 0.0,
        "cost_reported": cost is not None,
        "prompt_tokens": token_usage.get("prompt_tokens", 0),
        "completion_tokens": token_usage.get("completion_tokens", 0),
        "reasoning_tokens": (token_usage.get("completion_tokens_details") or {}).get(
            "reasoning_tokens", 0
        ),
        "served_model": meta.get("model_name"),
        "provider": meta.get("provider"),
        "generation_id": meta.get("id"),
    }


# ---------------------------------------------------------------- retries / concurrency

_RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_semaphores: dict[tuple[int, str], asyncio.Semaphore] = {}


def provider_key(model: str) -> str:
    return model.split("/", 1)[0]


def provider_semaphore(model: str, limit: int) -> asyncio.Semaphore:
    """One semaphore per (event loop, provider) — safe across pytest's per-test loops."""
    key = (id(asyncio.get_running_loop()), provider_key(model))
    sem = _semaphores.get(key)
    if sem is None:
        sem = _semaphores[key] = asyncio.Semaphore(limit)
    return sem


class RpmLimiter:
    """Sliding-window requests-per-minute cap, one per (event loop, model)."""

    def __init__(self, rpm: int) -> None:
        self.rpm = rpm
        self._sent: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._sent = [t for t in self._sent if now - t < 60.0]
                if len(self._sent) < self.rpm:
                    self._sent.append(now)
                    return
                await asyncio.sleep(60.0 - (now - self._sent[0]) + 0.05)


_rpm_limiters: dict[tuple[int, str], RpmLimiter] = {}


def rpm_limiter(model: str, settings: Settings) -> RpmLimiter | None:
    rpm = settings.rpm_limits.get(model)
    if not rpm:
        return None
    key = (id(asyncio.get_running_loop()), model)
    lim = _rpm_limiters.get(key)
    if lim is None:
        lim = _rpm_limiters[key] = RpmLimiter(rpm)
    return lim


class OpenRouterBodyError(RuntimeError):
    """HTTP 200 whose body is `{"error": {"code", "message", "metadata"}}` (OpenRouter reports
    upstream failures this way); retried like the equivalent HTTP status."""

    def __init__(self, body: dict[str, Any]) -> None:
        super().__init__(f"OpenRouter error body: {str(body)[:300]}")
        self.body = body
        err = body.get("error")
        code = err.get("code") if isinstance(err, dict) else None
        self.code = code
        self.status_code = code if isinstance(code, int) else None


def _error_parts(exc: BaseException) -> tuple[int | None, dict[str, Any], Any]:
    """(status, body, response headers) of an OpenRouter error, whichever client raised it."""
    if isinstance(exc, openai.APIStatusError):
        body = exc.body if isinstance(exc.body, dict) else {}
        return exc.status_code, body, exc.response.headers
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            body = exc.response.json()
        except ValueError:
            body = {}
        body = body if isinstance(body, dict) else {}
        return exc.response.status_code, body, exc.response.headers
    if isinstance(exc, OpenRouterBodyError):
        return exc.status_code, exc.body, {}
    return None, {}, {}


def _rate_limit_reset_s(exc: BaseException) -> float | None:
    """Seconds until OpenRouter's X-RateLimit-Reset (epoch ms), if the 429 carries it."""
    status, body, resp_headers = _error_parts(exc)
    if status != 429:
        return None
    err = body.get("error") if isinstance(body.get("error"), dict) else body
    headers = (err.get("metadata") or {}).get("headers") or {}
    reset = headers.get("X-RateLimit-Reset") or resp_headers.get("x-ratelimit-reset")
    try:
        return max(0.0, float(reset) / 1000.0 - time.time())
    except (TypeError, ValueError):
        return None


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRY_STATUS
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code in _RETRY_STATUS
    if isinstance(exc, OpenRouterBodyError):
        # no code at all: unknown upstream failure, retry; a symbolic code (invalid_model)
        # is a client error that will never succeed (B8)
        if exc.code is None:
            return True
        return exc.status_code in _RETRY_STATUS
    return isinstance(exc, openai.APIConnectionError | openai.APITimeoutError)


@dataclass
class RetryStats:
    """Per `call_with_retry`: `call_ms` is the successful HTTP attempt only (the latency we
    report); `queue_ms` = provider semaphore + RPM limiter waits; `retry_ms` = failed attempts
    + backoff sleeps. RPM buckets are shared across roles on purpose: queueing is excluded."""

    attempts: int = 0
    errors: list[str] = field(default_factory=list)
    call_ms: float = 0.0
    queue_ms: float = 0.0
    retry_ms: float = 0.0


async def call_with_retry[T](
    fn: Callable[[], Awaitable[T]],
    *,
    model: str,
    settings: Settings,
    stats: RetryStats | None = None,
) -> T:
    """Run `fn` under the provider semaphore with tenacity backoff on transient errors."""
    stats = stats if stats is not None else RetryStats()

    def _record(state: RetryCallState) -> None:
        if state.outcome is not None and state.outcome.failed:
            stats.errors.append(repr(state.outcome.exception())[:200])

    backoff = wait_exponential_jitter(initial=0.5, max=8.0)

    def _wait(state: RetryCallState) -> float:
        exc = state.outcome.exception() if state.outcome else None
        reset = _rate_limit_reset_s(exc) if exc else None
        if reset is not None:
            return min(reset + 0.5, settings.max_rate_limit_wait_s)
        return backoff(state)

    limiter = rpm_limiter(model, settings)
    retrying = AsyncRetrying(
        stop=stop_after_attempt(settings.http_retries + 1),
        wait=_wait,
        retry=retry_if_exception(_is_retryable),
        after=_record,
        reraise=True,
    )
    t_start = time.perf_counter()
    async with provider_semaphore(model, settings.max_concurrency_per_provider):
        stats.queue_ms += (time.perf_counter() - t_start) * 1000
        async for attempt in retrying:
            with attempt:
                if limiter is not None:
                    t_q = time.perf_counter()
                    await limiter.acquire()
                    stats.queue_ms += (time.perf_counter() - t_q) * 1000
                stats.attempts += 1
                t_call = time.perf_counter()
                result = await fn()
                t_end = time.perf_counter()
                stats.call_ms = (t_end - t_call) * 1000
                stats.retry_ms = max(0.0, (t_end - t_start) * 1000 - stats.queue_ms - stats.call_ms)
                return result
    raise AssertionError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------- embeddings


@dataclass
class EmbeddingResult:
    vectors: np.ndarray  # shape (n, dim), float32
    cost_usd: float
    served_model: str | None
    provider: str | None
    prompt_tokens: int
    latency_ms: float  # successful HTTP attempt only (see RetryStats)
    attempts: int = 1
    queue_ms: float = 0.0
    retry_ms: float = 0.0


class EmbeddingsClient:
    """OpenRouter `/embeddings` (OpenAI-compatible) with cost and provider capture."""

    def __init__(
        self,
        settings: Settings,
        model: str,
        *,
        provider: ProviderPrefs | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.model = model
        self.provider = provider
        self._http = http

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.settings.request_timeout_s)
        return self._http

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        body: dict[str, Any] = {"model": self.model, "input": texts}
        body.update(provider_extra_body(self.provider))
        headers = {"Authorization": f"Bearer {self.settings.openrouter_api_key.get_secret_value()}"}
        url = f"{self.settings.openrouter_base_url.rstrip('/')}/embeddings"

        async def _post() -> dict[str, Any]:
            resp = await self._client().post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if "data" not in data:
                raise OpenRouterBodyError(data if isinstance(data, dict) else {"error": data})
            return data

        stats = RetryStats()
        data = await call_with_retry(_post, model=self.model, settings=self.settings, stats=stats)
        rows = sorted(data["data"], key=lambda r: r["index"])
        usage = data.get("usage") or {}
        return EmbeddingResult(
            vectors=np.asarray([r["embedding"] for r in rows], dtype=np.float32),
            cost_usd=float(usage.get("cost") or 0.0),
            served_model=data.get("model"),
            provider=data.get("provider"),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            latency_ms=stats.call_ms,
            attempts=stats.attempts,
            queue_ms=stats.queue_ms,
            retry_ms=stats.retry_ms,
        )

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()


# ---------------------------------------------------------------- slug validation


def configured_models(settings: Settings) -> tuple[set[str], set[str]]:
    """(chat slugs, embedding slugs) referenced by the experiment config."""
    chat: set[str] = set()
    emb: set[str] = set()
    s = settings.strategies
    for cfg in (s.llm, s.jev):
        if cfg is not None:
            chat.add(cfg.model)
    if s.embedding is not None:
        emb.add(s.embedding.model)
    if settings.executor is not None:
        chat.add(settings.executor.model)
    return chat, emb


async def validate_models(
    settings: Settings, http: httpx.AsyncClient | None = None
) -> dict[str, list[str]]:
    """Fail fast if a configured slug is missing. Returns slug -> supported_parameters."""
    chat, emb = configured_models(settings)
    base = settings.openrouter_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}"}
    own = http is None
    client = http or httpx.AsyncClient(timeout=settings.request_timeout_s)
    try:

        async def _get(path: str) -> list[dict[str, Any]]:
            async def _call() -> list[dict[str, Any]]:
                r = await client.get(f"{base}{path}", headers=headers)
                r.raise_for_status()
                return r.json()["data"]

            return await call_with_retry(_call, model="openrouter/catalog", settings=settings)

        chat_models = await _get("/models") if chat else []
        emb_models = await _get("/embeddings/models") if emb else []
    finally:
        if own:
            await client.aclose()

    known_chat = {m["id"]: list(m.get("supported_parameters") or []) for m in chat_models}
    known_emb = {m["id"]: list(m.get("supported_parameters") or []) for m in emb_models}
    missing = sorted((chat - known_chat.keys()) | (emb - known_emb.keys()))
    if missing:
        raise UnknownModelError(f"OpenRouter does not list configured model(s): {missing}")
    return {slug: (known_chat.get(slug) or known_emb.get(slug) or []) for slug in chat | emb}
