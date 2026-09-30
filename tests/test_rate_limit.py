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
