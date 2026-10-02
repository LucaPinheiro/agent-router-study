import asyncio
import time

import httpx
import openai
import pytest

from routing_study.llm import RetryStats, RpmLimiter, _rate_limit_reset_s, call_with_retry
from routing_study.settings import Settings


def _429(reset_ms: float) -> openai.RateLimitError:
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    body = {"code": 429, "metadata": {"headers": {"X-RateLimit-Reset": str(int(reset_ms))}}}
    return openai.RateLimitError("rate", response=httpx.Response(429, request=req), body=body)


def test_reset_header_parsed() -> None:
    wait = _rate_limit_reset_s(_429(time.time() * 1000 + 3000))
    assert wait is not None and 2.0 < wait <= 3.0


async def test_retry_waits_for_reset_then_succeeds() -> None:
    settings = Settings(http_retries=2, rpm_limits={})
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _429(time.time() * 1000 + 300)
        return "ok"

    stats = RetryStats()
    t0 = time.monotonic()
    assert await call_with_retry(fn, model="m/x", settings=settings, stats=stats) == "ok"
    assert time.monotonic() - t0 >= 0.3
    assert stats.attempts == 2


async def test_rpm_limiter_blocks_over_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    lim = RpmLimiter(2)
    await lim.acquire()
    await lim.acquire()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(lim.acquire(), timeout=0.2)


async def test_retry_stats_split_queue_backoff_and_call_time() -> None:
    """B2: only the successful HTTP attempt is call time; queue and backoff are separate."""
    settings = Settings(
        _env_file=None,
        http_retries=2,
        rpm_limits={},
        max_concurrency_per_provider=1,
        max_rate_limit_wait_s=65.0,
    )
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _429(time.time() * 1000)  # reset now -> ~0.5 s wait
        await asyncio.sleep(0.05)
        return "ok"

    async def hog() -> None:
        async def slow() -> None:
            await asyncio.sleep(0.2)

        await call_with_retry(slow, model="q/x", settings=settings)

    stats = RetryStats()
    blocker = asyncio.create_task(hog())
    await asyncio.sleep(0)  # hog holds the provider semaphore first
    assert await call_with_retry(fn, model="q/y", settings=settings, stats=stats) == "ok"
    await blocker
    assert stats.queue_ms >= 150
    assert stats.retry_ms >= 400
    assert 40 <= stats.call_ms < 150


# ---------------------------------------------------------------- F1: Bedrock throttling


def _client_error(code: str) -> Exception:
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": code, "Message": "x"}}, "Converse")


def _fast_throttle(**kw: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "http_retries": 1,
        "rpm_limits": {},
        "throttle_retry_budget_s": 5.0,
        "throttle_backoff_initial_s": 0.01,
        "throttle_backoff_max_s": 0.05,
    }
    return Settings(**{**base, **kw})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "code",
    [
        "ThrottlingException",
        "ServiceUnavailableException",
        "ModelNotReadyException",
        "ModelTimeoutException",
    ],
)
async def test_bedrock_capacity_errors_retry_past_http_retries(code: str) -> None:
    """F1: throttling-class errors are bounded by the time budget, not by http_retries."""
    settings = _fast_throttle()
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        if calls <= 4:  # http_retries=1 would give up after 2 attempts
            raise _client_error(code)
        await asyncio.sleep(0.02)
        return "ok"

    stats = RetryStats()
    assert await call_with_retry(fn, model="global.anthropic.x", settings=settings, stats=stats)
    assert stats.attempts == 5 and len(stats.errors) == 4
    assert stats.call_ms < 200  # only the successful attempt is latency
    assert stats.retry_ms > 0


@pytest.mark.parametrize("status", [429, 503])
async def test_http_429_503_are_throttle_class(status: int) -> None:
    settings = _fast_throttle()
    req = httpx.Request("POST", "https://x/v1/chat")
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        if calls <= 3:
            raise httpx.HTTPStatusError(
                "busy", request=req, response=httpx.Response(status, request=req)
            )
        return "ok"

    assert await call_with_retry(fn, model="m/x", settings=settings) == "ok"
    assert calls == 4


async def test_throttle_gives_up_when_the_time_budget_is_spent() -> None:
    settings = _fast_throttle(throttle_retry_budget_s=0.3)
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        raise _client_error("ThrottlingException")

    t0 = time.monotonic()
    with pytest.raises(Exception, match="ThrottlingException"):
        await call_with_retry(fn, model="global.anthropic.x", settings=settings)
    elapsed = time.monotonic() - t0
    assert 0.25 <= elapsed < 1.0 and calls > 2


async def test_non_throttle_bedrock_errors_are_not_retried() -> None:
    settings = _fast_throttle()
    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        raise _client_error("ValidationException")

    with pytest.raises(Exception, match="ValidationException"):
        await call_with_retry(fn, model="global.anthropic.x", settings=settings)
    assert calls == 1


async def test_rpm_cap_comes_from_the_model_block_by_actual_id() -> None:
    """F1: rpm caps are keyed by the configured model id of any provider, set per model."""
    from routing_study.llm import rpm_limiter
    from routing_study.settings import ExecutorConfig, LLMStrategy, StrategiesConfig

    bedrock_id = "global.anthropic.claude-sonnet-5"
    settings = Settings(
        _env_file=None,
        rpm_limits={"typesafe/jev-router": 40},
        strategies=StrategiesConfig(
            llm=LLMStrategy(provider="bedrock", model=bedrock_id, temperature=None, rpm_limit=30),
            llm_local=LLMStrategy(provider="ollama", model="qwen3:8b", num_ctx=8192, rpm_limit=90),
        ),
        executor=ExecutorConfig(provider="bedrock", model=bedrock_id, rpm_limit=20),
    )
    lim = rpm_limiter(bedrock_id, settings)
    assert lim is not None and lim.rpm == 20  # shared id: the tighter cap wins
    served = rpm_limiter("qwen3:8b-ctx8192", settings)
    assert served is not None and served.rpm == 90
    assert rpm_limiter("typesafe/jev-router", settings).rpm == 40  # type: ignore[union-attr]
    assert rpm_limiter("other/model", settings) is None


def test_rpm_limit_does_not_change_the_config_hash() -> None:
    from routing_study.settings import LLMStrategy

    a = LLMStrategy(provider="bedrock", model="m", temperature=None)
    b = LLMStrategy(provider="bedrock", model="m", temperature=None, rpm_limit=5)
    assert a.model_dump_json() == b.model_dump_json()


def test_bedrock_sdk_retries_stay_off(tmp_path) -> None:
    """F1: botocore must not retry under `call_with_retry` (no double backoff, honest counts)."""
    from routing_study.llm import make_bedrock_chat

    s = Settings(_env_file=None)
    chat = make_bedrock_chat(s, "global.anthropic.claude-sonnet-5")
    assert chat._get_effective_config().retries == {"max_attempts": 0}  # 1 attempt in total
