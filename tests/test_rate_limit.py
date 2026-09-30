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
