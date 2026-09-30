"""Model clients for three providers: chat, embeddings, model validation.

- openrouter: ChatOpenAI; cost from OpenRouter's `usage.cost` (`usage: {include: true}`).
- bedrock:    ChatBedrockConverse (default AWS credential chain); cost = token usage x the
              price table (`budget.prices_path`), cache read/write tokens included.
- ollama:     local, OpenAI-compatible `/v1` (chat + embeddings); cost 0, tokens recorded.
Every chat response carries the same `response_metadata["token_usage"]` shape (OpenAI style:
prompt/completion tokens, `cost`, `prompt_tokens_details.cached_tokens/cache_write_tokens`),
so `extract_call_usage` and the tracing callbacks are provider-agnostic. Every call goes
through the spend ledger (`routing_study.budget`): reserved before, recorded after.
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

import botocore.exceptions
import httpx
import httpx2
import numpy as np
import openai
from langchain_aws import ChatBedrockConverse
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import Field
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from routing_study.budget import CallMeter, Price, SpendLedger, ledger_for, prices_for
from routing_study.settings import (
    ModelEndpoint,
    ProviderPrefs,
    ReasoningPrefs,
    Settings,
)


class UnknownModelError(RuntimeError):
    pass


# ---------------------------------------------------------------- metering


def _text_len(messages: list[BaseMessage]) -> int:
    n = 0
    for m in messages:
        if isinstance(m.content, str):
            n += len(m.content)
        else:
            n += sum(len(str(b.get("text", b)) if isinstance(b, dict) else b) for b in m.content)
    return n


class _Metered:
    """Reserve (upper bound) -> call -> record, around each generation. Subclasses declare
    `ledger`, `price` and `max_tokens`; the upper bound over-counts the prompt (1 token per
    2 characters, no cache discount) so a reservation is never below the real cost."""

    ledger: SpendLedger | None
    price: Price | None
    provider_name: str

    def _meter(self, messages: list[BaseMessage], **kwargs: Any) -> CallMeter:
        upper = 0.0
        if self.price is not None:
            out = kwargs.get("max_tokens") or getattr(self, "max_tokens", None) or 4096
            upper = self.price.cost(prompt_tokens=_text_len(messages) // 2, completion_tokens=out)
        model = getattr(self, "model_name", None) or getattr(self, "model_id", "")
        return CallMeter(self.ledger, self.provider_name, model, upper)


def result_usage(result: ChatResult) -> dict[str, Any]:
    """Usage of a raw `_agenerate` result: langchain-core only merges `llm_output` (where
    ChatOpenAI keeps `token_usage`) into the message metadata AFTER `_agenerate` returns."""
    msg = result.generations[0].message if result.generations else None
    if not isinstance(msg, AIMessage):
        return extract_call_usage(None)
    meta = {**(result.llm_output or {}), **msg.response_metadata}
    return extract_call_usage(msg.model_copy(update={"response_metadata": meta}))


class OpenRouterChat(_Metered, ChatOpenAI):
    """ChatOpenAI that keeps OpenRouter's top-level `provider` in `response_metadata`."""

    ledger: Any = Field(default=None, exclude=True)
    price: Any = Field(default=None, exclude=True)
    provider_name: str = Field(default="openrouter", exclude=True)

    async def _agenerate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kw: Any
    ) -> ChatResult:
        with self._meter(messages, **kw) as meter:
            result = await super()._agenerate(messages, stop, run_manager, **kw)
            meter.done(result_usage(result))
        return result

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


class OllamaChat(_Metered, ChatOpenAI):
    """ChatOpenAI against Ollama's OpenAI-compatible `/v1`: cost 0, provider `ollama`.
    Thinking (Qwen3) is switched by `reasoning_effort` ("none" = off); `logprobs=True`
    returns per-token logprobs in `response_metadata["logprobs"]`."""

    ledger: Any = Field(default=None, exclude=True)
    price: Any = Field(default=None, exclude=True)
    provider_name: str = Field(default="ollama", exclude=True)

    async def _agenerate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kw: Any
    ) -> ChatResult:
        with self._meter(messages, **kw) as meter:
            result = await super()._agenerate(messages, stop, run_manager, **kw)
            out = result.llm_output = result.llm_output or {}
            out["provider"] = "ollama"
            out["token_usage"] = {**(out.get("token_usage") or {}), "cost": 0.0}
            meter.done(result_usage(result))
        return result


def bedrock_cache_points(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Anthropic-style `cache_control` on a content block -> the same block + a Converse
    `cachePoint` after it (langchain-aws ignores `cache_control` inside blocks)."""
    out: list[BaseMessage] = []
    for m in messages:
        if isinstance(m.content, str) or not any(
            isinstance(b, dict) and "cache_control" in b for b in m.content
        ):
            out.append(m)
            continue
        blocks: list[Any] = []
        for b in m.content:
            if isinstance(b, dict) and "cache_control" in b:
                blocks.append({k: v for k, v in b.items() if k != "cache_control"})
                blocks.append({"cachePoint": {"type": "default"}})
            else:
                blocks.append(b)
        out.append(m.model_copy(update={"content": blocks}))
    return out


def bedrock_token_usage(msg: AIMessage, price: Price | None) -> dict[str, Any]:
    """OpenAI-shaped `token_usage` (+ cost from the price table) from Converse usage.

    langchain-aws: `input_tokens` = uncached + cache read + cache write; the write count is
    in `cache_creation`, or split by TTL in `ephemeral_5m/1h_input_tokens` (then
    `cache_creation` is 0)."""
    um = msg.usage_metadata or {}
    det: dict[str, Any] = dict(um.get("input_token_details") or {})
    w5 = int(det.get("ephemeral_5m_input_tokens") or 0)
    w1h = int(det.get("ephemeral_1h_input_tokens") or 0)
    w5 += int(det.get("cache_creation") or 0)
    read = int(det.get("cache_read") or 0)
    prompt, completion = int(um.get("input_tokens") or 0), int(um.get("output_tokens") or 0)
    cost = (
        price.cost(
            prompt_tokens=prompt,
            completion_tokens=completion,
            cache_read=read,
            cache_write=w5,
            cache_write_1h=w1h,
        )
        if price is not None
        else None
    )
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "cost": cost,
        "prompt_tokens_details": {"cached_tokens": read, "cache_write_tokens": w5 + w1h},
    }


class BedrockChat(_Metered, ChatBedrockConverse):
    """ChatBedrockConverse + cache points, unified `token_usage`/cost and metering.

    - `temperature=None` is never sent (Sonnet 5 on Bedrock rejects it).
    - SDK retries are off (`max_retries=0`): `call_with_retry` owns ThrottlingException.
    - `tool_choice="none"` has no Converse equivalent: it is sent as Anthropic's native
      `tool_choice: {type: none}` via `additional_model_request_fields` (on a copy).
    - `parallel_tool_calls` is dropped (Converse has no such flag)."""

    ledger: Any = Field(default=None, exclude=True)
    price: Any = Field(default=None, exclude=True)
    provider_name: str = Field(default="bedrock", exclude=True)

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kw: Any
    ) -> ChatResult:
        messages = bedrock_cache_points(messages)
        with self._meter(messages, **kw) as meter:
            result = super()._generate(messages, stop, run_manager, **kw)
            for gen in result.generations:
                if isinstance(gen.message, AIMessage):
                    meta = gen.message.response_metadata
                    meta["token_usage"] = bedrock_token_usage(gen.message, self.price)
                    meta["model_name"] = self.model_id
                    meta["provider"] = "bedrock"
            usage = result_usage(result)
            result.llm_output = {
                "token_usage": result.generations[0].message.response_metadata["token_usage"],
                "model_name": self.model_id,
                "provider": "bedrock",
            }
            meter.done(usage)
        return result

    def _combine_llm_outputs(self, llm_outputs: list[dict | None]) -> dict:
        return next((o for o in llm_outputs if o), {})

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Runnable:
        kwargs.pop("parallel_tool_calls", None)
        if tool_choice == "none":  # a copy whose requests carry the native tool_choice
            fields = {**(self.additional_model_request_fields or {})}
            fields["tool_choice"] = {"type": "none"}
            clone = self.model_copy(update={"additional_model_request_fields": fields})
            return ChatBedrockConverse.bind_tools(clone, tools, **kwargs)
        return super().bind_tools(tools, tool_choice=tool_choice, **kwargs)


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
    base_url: str | None = None,
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
        "base_url": base_url or settings.openrouter_base_url,
        "api_key": settings.openrouter_api_key.get_secret_value() or "missing",
        "extra_body": provider_extra_body(provider, reasoning),
        "max_retries": 0,
        "timeout": settings.request_timeout_s,
        "ledger": ledger_for(settings),
        "price": prices_for(settings).get(("openrouter", model)),
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    kwargs["http_async_client"] = (
        _CHAT_HTTP_CLIENT if http_async_client is None else http_async_client
    )
    kwargs.update({k: v for k, v in params.items() if v is not None})
    return OpenRouterChat(**kwargs)


def make_bedrock_chat(
    settings: Settings,
    model: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    region: str | None = None,
    reasoning: ReasoningPrefs | None = None,
) -> BedrockChat:
    """Bedrock Converse with the default AWS credential chain; `temperature=None` is omitted."""
    if reasoning is not None and reasoning.enabled:
        raise ValueError(f"{model}: reasoning on Bedrock is not supported by this study")
    price = prices_for(settings).get(("bedrock", model))
    if price is None:  # an unpriced paid model would slip past the budget guard
        raise ValueError(f"no bedrock price for {model!r} in {settings.budget.prices_path}")
    kwargs: dict[str, Any] = {
        "model": model,
        "region_name": region or settings.bedrock_region,
        "max_retries": 0,
        "timeout": int(settings.request_timeout_s),
        "ledger": ledger_for(settings),
        "price": price,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return BedrockChat(**kwargs)


def make_ollama_chat(
    settings: Settings,
    model: str,
    *,
    temperature: float | None = None,
    seed: int | None = None,
    max_tokens: int | None = None,
    base_url: str | None = None,
    reasoning: ReasoningPrefs | None = None,
    logprobs: bool = False,
    http_async_client: Any | None = None,
) -> OllamaChat:
    """Local model via Ollama `/v1`. Thinking follows `reasoning` (off by default:
    `reasoning_effort: none`); `logprobs` asks for per-token logprobs of the reply."""
    think = reasoning is not None and reasoning.enabled
    kwargs: dict[str, Any] = {
        "model": model,
        "base_url": base_url or settings.ollama_base_url,
        "api_key": "ollama",
        "max_retries": 0,
        "timeout": settings.request_timeout_s,
        "reasoning_effort": (reasoning.effort or "medium") if think and reasoning else "none",
        "ledger": ledger_for(settings),
        "price": None,
        "http_async_client": (
            _CHAT_HTTP_CLIENT if http_async_client is None else http_async_client
        ),
    }
    if logprobs:
        kwargs["logprobs"] = True
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    kwargs.update(
        {k: v for k, v in {"temperature": temperature, "seed": seed}.items() if v is not None}
    )
    return OllamaChat(**kwargs)


def chat_model_for(
    settings: Settings, cfg: ModelEndpoint, *, supported_parameters: Iterable[str] | None = None
) -> BaseChatModel:
    """The chat client of a config block (an LLM or jev strategy, or the executor)."""
    temperature = getattr(cfg, "temperature", None)
    seed = getattr(cfg, "seed", None)
    reasoning = getattr(cfg, "reasoning", None)
    max_tokens = getattr(cfg, "max_tokens", None)
    if cfg.provider == "bedrock":
        return make_bedrock_chat(
            settings,
            cfg.model,
            temperature=temperature,
            max_tokens=max_tokens,
            region=cfg.region,
            reasoning=reasoning,
        )
    if cfg.provider == "ollama":
        return make_ollama_chat(
            settings,
            cfg.served_name,
            temperature=temperature,
            seed=seed,
            max_tokens=max_tokens,
            base_url=cfg.base_url,
            reasoning=reasoning,
            logprobs=getattr(cfg, "confidence", None) == "logprob",
        )
    return make_chat_model(
        settings,
        cfg.model,
        temperature=temperature,
        seed=seed,
        provider=cfg.openrouter,
        reasoning=reasoning,
        max_tokens=max_tokens,
        supported_parameters=supported_parameters,
        base_url=cfg.base_url,
    )


def structured_runnable(chat: Any, schema: dict[str, Any], *, json_mode: bool = False) -> Runnable:
    """Structured output constrained to `schema`, `include_raw=True` on every provider.

    - Bedrock: forced tool use (`function_calling`); Sonnet 5 on Bedrock rejects the
      native json_schema output format ("output_config.format: Extra inputs").
    - OpenRouter / Ollama: `response_format` strict json_schema (Ollama compiles it into a
      grammar, so the enum is enforced token by token).
    - `json_mode`: plain JSON object (`response_format: json_object`), the schema is only
      validated afterwards. Used for logprob confidence: under a schema grammar Ollama
      forces sub-word tokens the model would not pick, and their logprobs are meaningless."""
    if isinstance(chat, ChatBedrockConverse):
        return chat.with_structured_output(schema, method="function_calling", include_raw=True)
    if json_mode:
        return chat.with_structured_output(schema, method="json_mode", include_raw=True)
    return chat.with_structured_output(schema, method="json_schema", include_raw=True, strict=True)


def extract_call_usage(msg: AIMessage | None) -> dict[str, Any]:
    """Unified usage of one chat response, any provider: cost (USD), prompt/completion
    tokens, cache read/write tokens, served model and provider."""
    if msg is None:
        return {"cost_usd": 0.0}
    meta = msg.response_metadata or {}
    token_usage = meta.get("token_usage") or {}
    details = token_usage.get("prompt_tokens_details") or {}
    cost = token_usage.get("cost")
    um = msg.usage_metadata or {}  # LangChain's own counts, when the raw usage is not kept
    um_details: dict[str, Any] = dict(um.get("input_token_details") or {})
    return {
        "cost_usd": float(cost) if cost is not None else 0.0,
        "cost_reported": cost is not None,
        "prompt_tokens": token_usage.get("prompt_tokens", um.get("input_tokens", 0)),
        "completion_tokens": token_usage.get("completion_tokens", um.get("output_tokens", 0)),
        "reasoning_tokens": (token_usage.get("completion_tokens_details") or {}).get(
            "reasoning_tokens", 0
        ),
        "cache_read": int(details.get("cached_tokens") or um_details.get("cache_read") or 0),
        "cache_write": int(
            details.get("cache_write_tokens") or um_details.get("cache_creation") or 0
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


# Bedrock: throttling / capacity / transient server errors (ClientError code)
_BEDROCK_RETRY = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelNotReadyException",
    "ModelTimeoutException",
    "TooManyRequestsException",
}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, botocore.exceptions.ClientError):
        return exc.response.get("Error", {}).get("Code") in _BEDROCK_RETRY
    if isinstance(exc, botocore.exceptions.ConnectionError | botocore.exceptions.ReadTimeoutError):
        return True
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
    provider: str | None = None,
) -> T:
    """Run `fn` under the provider semaphore with tenacity backoff on transient errors.

    `provider="ollama"`: one semaphore for the whole local server, sized to its request
    slots (`ollama_num_parallel`), so waiting for a slot is `queue_ms`, not model latency."""
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
    sem = (
        provider_semaphore("ollama", settings.ollama_num_parallel)
        if provider == "ollama"
        else provider_semaphore(model, settings.max_concurrency_per_provider)
    )
    async with sem:
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
    """OpenAI-compatible `/embeddings` (OpenRouter or Ollama `/v1`) with cost, provider
    capture and ledger metering. `query_instruction` prefixes QUERIES only (`embed_query`);
    documents go through `embed` unchanged (instruction-aware models, e.g. Qwen3-Embedding)."""

    def __init__(
        self,
        settings: Settings,
        model: str,
        *,
        provider: ProviderPrefs | None = None,
        http: httpx.AsyncClient | None = None,
        backend: str = "openrouter",
        base_url: str | None = None,
        query_instruction: str | None = None,
    ) -> None:
        self.settings = settings
        self.model = model
        self.provider = provider
        self.backend = backend
        self.query_instruction = query_instruction
        default = settings.ollama_base_url if backend == "ollama" else settings.openrouter_base_url
        self.base_url = (base_url or default).rstrip("/")
        self._http = http

    @classmethod
    def for_config(cls, settings: Settings, cfg: Any) -> EmbeddingsClient:
        return cls(
            settings,
            cfg.served_name,
            provider=cfg.openrouter,
            backend=cfg.provider,
            base_url=cfg.base_url,
            query_instruction=cfg.query_instruction,
        )

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.settings.request_timeout_s)
        return self._http

    def query_text(self, text: str) -> str:
        return f"{self.query_instruction}{text}" if self.query_instruction else text

    async def embed_query(self, text: str) -> EmbeddingResult:
        return await self.embed([self.query_text(text)])

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if self.backend not in ("openrouter", "ollama"):
            raise ValueError(f"embeddings provider {self.backend!r} is not supported")
        body: dict[str, Any] = {"model": self.model, "input": texts}
        headers: dict[str, str] = {}
        if self.backend == "openrouter":
            body.update(provider_extra_body(self.provider))
            key = self.settings.openrouter_api_key.get_secret_value()
            headers["Authorization"] = f"Bearer {key}"
        url = f"{self.base_url}/embeddings"

        async def _post() -> dict[str, Any]:
            resp = await self._client().post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if "data" not in data:
                raise OpenRouterBodyError(data if isinstance(data, dict) else {"error": data})
            return data

        stats = RetryStats()
        with CallMeter(ledger_for(self.settings), self.backend, self.model, 0.0) as meter:
            data = await call_with_retry(
                _post, model=self.model, settings=self.settings, stats=stats, provider=self.backend
            )
            usage = data.get("usage") or {}
            cost = 0.0 if self.backend == "ollama" else float(usage.get("cost") or 0.0)
            meter.done(
                {
                    "cost_usd": cost,
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "served_model": data.get("model"),
                },
                kind="embedding",
                inputs=len(texts),
            )
        rows = sorted(data["data"], key=lambda r: r["index"])
        return EmbeddingResult(
            vectors=np.asarray([r["embedding"] for r in rows], dtype=np.float32),
            cost_usd=cost,
            served_model=data.get("model"),
            provider=data.get("provider")
            or (self.backend if self.backend != "openrouter" else None),
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


def configured_models(
    settings: Settings, names: set[str] | None = None
) -> tuple[set[str], set[str]]:
    """(chat slugs, embedding slugs) of the OpenRouter models the experiment config uses."""
    chat: set[str] = set()
    emb: set[str] = set()
    for kind, cfg in model_configs(settings, names):
        if cfg.provider == "openrouter":
            (emb if kind == "embedding" else chat).add(cfg.model)
    return chat, emb


def model_configs(
    settings: Settings, names: set[str] | None = None
) -> list[tuple[str, ModelEndpoint]]:
    """(strategy name | "executor", model block) of every configured model, or only of the
    strategies/roles in `names` (`hybrid` uses the embedding model)."""
    s = settings.strategies
    out: list[tuple[str, ModelEndpoint]] = [("embedding", s.embedding)] if s.embedding else []
    out += list(s.llm_strategies().items())
    if s.jev is not None:
        out.append(("jev", s.jev))
    if settings.executor is not None:
        out.append(("executor", settings.executor))
    if names is not None:
        wanted = names | ({"embedding"} if "hybrid" in names else set())
        out = [(n, c) for n, c in out if n in wanted]
    return out


async def _check_ollama(
    settings: Settings, names: set[str] | None, client: httpx.AsyncClient
) -> None:
    """Every Ollama model used must be pulled (`/api/tags` of the server)."""
    by_base: dict[str, set[str]] = {}
    for _, cfg in model_configs(settings, names):
        if cfg.provider == "ollama":
            base = (cfg.base_url or settings.ollama_base_url).rstrip("/").removesuffix("/v1")
            by_base.setdefault(base, set()).add(cfg.model)
    for base, wanted in by_base.items():
        r = await client.get(f"{base}/api/tags")
        r.raise_for_status()
        have = {m["name"] for m in r.json().get("models", [])}
        missing = sorted(wanted - have)
        if missing:
            raise UnknownModelError(f"Ollama at {base} has not pulled: {missing}")


def _ollama_base(settings: Settings, cfg: ModelEndpoint) -> str:
    return (cfg.base_url or settings.ollama_base_url).rstrip("/").removesuffix("/v1")


async def unload_ollama(settings: Settings, keep: set[str] = frozenset()) -> list[str]:
    """Unload every model resident in the local server except `keep` (served names)."""
    base = settings.ollama_base_url.rstrip("/").removesuffix("/v1")
    unloaded: list[str] = []
    async with httpx.AsyncClient(timeout=120) as client:
        for m in (await client.get(f"{base}/api/ps")).json().get("models", []):
            if m["name"] in keep:
                continue
            body = {"model": m["name"], "keep_alive": 0}  # unloads embedders too
            (await client.post(f"{base}/api/generate", json=body)).raise_for_status()
            unloaded.append(m["name"])
    return unloaded


async def preload_ollama(
    settings: Settings, names: set[str] | None = None, keep_alive: str = "30m"
) -> dict[str, float]:
    """Make the run's local models the only resident ones, then load them before timing
    (so a model load never lands in a measured latency). A `num_ctx` model is created first
    as its derived tag (`/api/create` from the base tag: no weight copy). Returns served
    name -> load seconds."""
    cfgs = {c.served_name: c for _, c in model_configs(settings, names) if c.provider == "ollama"}
    if not cfgs:
        return {}
    await unload_ollama(settings, keep=set(cfgs))
    out: dict[str, float] = {}
    async with httpx.AsyncClient(timeout=600) as client:
        for name, cfg in cfgs.items():
            base = _ollama_base(settings, cfg)
            if cfg.num_ctx:
                body = {"model": name, "from": cfg.model, "parameters": {"num_ctx": cfg.num_ctx}}
                (
                    await client.post(f"{base}/api/create", json={**body, "stream": False})
                ).raise_for_status()
            t0 = time.perf_counter()
            if cfg is settings.strategies.embedding:
                body = {"model": name, "input": "", "keep_alive": keep_alive}
                r = await client.post(f"{base}/api/embed", json=body)
            else:
                r = await client.post(
                    f"{base}/api/generate", json={"model": name, "keep_alive": keep_alive}
                )
            r.raise_for_status()
            out[name] = time.perf_counter() - t0
    return out


async def validate_models(
    settings: Settings, http: httpx.AsyncClient | None = None, names: set[str] | None = None
) -> dict[str, list[str]]:
    """Fail fast if a model is missing (OpenRouter catalog / Ollama tags): every configured
    one, or those of the strategies/roles in `names` (e.g. the run's routers + "executor").
    Returns OpenRouter slug -> supported_parameters. Bedrock ids are checked by the first
    call (no free catalog lookup for inference profiles)."""
    chat, emb = configured_models(settings, names)
    local = any(c.provider == "ollama" for _, c in model_configs(settings, names))
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
        if local:
            await _check_ollama(settings, names, client)
    finally:
        if own:
            await client.aclose()

    known_chat = {m["id"]: list(m.get("supported_parameters") or []) for m in chat_models}
    known_emb = {m["id"]: list(m.get("supported_parameters") or []) for m in emb_models}
    missing = sorted((chat - known_chat.keys()) | (emb - known_emb.keys()))
    if missing:
        raise UnknownModelError(f"OpenRouter does not list configured model(s): {missing}")
    return {slug: (known_chat.get(slug) or known_emb.get(slug) or []) for slug in chat | emb}
