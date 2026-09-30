"""OpenRouter clients: chat (LangChain ChatOpenAI), embeddings (/embeddings), slug validation.

- Cost comes from OpenRouter's `usage.cost` (`usage: {include: true}`); never estimated locally.
- The served model and provider are read from the response, not from config.
- Retries: tenacity with exponential backoff; concurrency: one asyncio semaphore per provider.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx
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

from routing_study.settings import ProviderPrefs, Settings

# Params we set that some OpenRouter models reject/ignore; dropped when the model's
# `supported_parameters` (from GET /models) does not list them.
_OPTIONAL_PARAMS = ("temperature", "seed")


class UnknownModelError(RuntimeError):
    pass


class OpenRouterChat(ChatOpenAI):
    """ChatOpenAI that keeps OpenRouter's top-level `provider` in `response_metadata`."""

    def _create_chat_result(
        self, response: dict | openai.BaseModel, generation_info: dict | None = None
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        provider = (response.get("provider") if isinstance(response, dict)
                    else getattr(response, "provider", None))
        if result.llm_output is not None and provider:
            result.llm_output["provider"] = provider
        for gen in result.generations:
            if isinstance(gen.message, AIMessage) and provider:
                gen.message.response_metadata["provider"] = provider
        return result


def provider_extra_body(prefs: ProviderPrefs | None) -> dict[str, Any]:
    body: dict[str, Any] = {"usage": {"include": True}}
    if prefs is not None and (prefs.order or not prefs.allow_fallbacks):
        provider: dict[str, Any] = {"allow_fallbacks": prefs.allow_fallbacks}
        if prefs.order:
            provider["order"] = list(prefs.order)
        body["provider"] = provider
    return body


def make_chat_model(
    settings: Settings,
    model: str,
    *,
    temperature: float | None = None,
    seed: int | None = None,
    provider: ProviderPrefs | None = None,
    max_tokens: int | None = None,
    supported_parameters: Iterable[str] | None = None,
    http_async_client: Any | None = None,
) -> OpenRouterChat:
    """ChatOpenAI against OpenRouter. Retries are owned by `call_with_retry`, not the SDK.

    `supported_parameters` (from `validate_models`) drops params the model does not accept;
    `None` means "unknown" and sends what was asked. `http_async_client` lets tests inject a
    plain `httpx.AsyncClient` (openai>=3 defaults to `httpx2`, which respx cannot mock).
    """
    params: dict[str, Any] = {"temperature": temperature, "seed": seed}
    if supported_parameters is not None:
        supported = set(supported_parameters)
        params = {k: (v if k in supported else None) for k, v in params.items()}
    kwargs: dict[str, Any] = {
        "model": model,
        "base_url": settings.openrouter_base_url,
        "api_key": settings.openrouter_api_key.get_secret_value() or "missing",
        "extra_body": provider_extra_body(provider),
        "max_retries": 0,
        "timeout": settings.request_timeout_s,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if http_async_client is not None:
        kwargs["http_async_client"] = http_async_client
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


def _rate_limit_reset_s(exc: BaseException) -> float | None:
    """Seconds until OpenRouter's X-RateLimit-Reset (epoch ms), if the 429 carries it."""
    if not (isinstance(exc, openai.APIStatusError) and exc.status_code == 429):
        return None
    body = exc.body if isinstance(exc.body, dict) else {}
    headers = (body.get("metadata") or {}).get("headers") or {}
    reset = headers.get("X-RateLimit-Reset") or exc.response.headers.get("x-ratelimit-reset")
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
    return isinstance(exc, openai.APIConnectionError | openai.APITimeoutError)


@dataclass
class RetryStats:
    attempts: int = 0
    errors: list[str] = field(default_factory=list)


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
    async with provider_semaphore(model, settings.max_concurrency_per_provider):
        async for attempt in retrying:
            with attempt:
                if limiter is not None:
                    await limiter.acquire()
                stats.attempts += 1
                return await fn()
    raise AssertionError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------- embeddings


@dataclass
class EmbeddingResult:
    vectors: np.ndarray  # shape (n, dim), float32
    cost_usd: float
    served_model: str | None
    provider: str | None
    prompt_tokens: int
    latency_ms: float
    attempts: int = 1


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
                raise RuntimeError(f"embeddings response without data: {str(data)[:300]}")
            return data

        stats = RetryStats()
        t0 = time.perf_counter()
        data = await call_with_retry(_post, model=self.model, settings=self.settings, stats=stats)
        latency_ms = (time.perf_counter() - t0) * 1000
        rows = sorted(data["data"], key=lambda r: r["index"])
        usage = data.get("usage") or {}
        return EmbeddingResult(
            vectors=np.asarray([r["embedding"] for r in rows], dtype=np.float32),
            cost_usd=float(usage.get("cost") or 0.0),
            served_model=data.get("model"),
            provider=data.get("provider"),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            latency_ms=latency_ms,
            attempts=stats.attempts,
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
