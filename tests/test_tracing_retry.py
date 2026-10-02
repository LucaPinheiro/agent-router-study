"""Langfuse resilience: retries with backoff, fail-fast preflight, no loop-bound async client."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from langfuse.api.core.api_error import ApiError

from routing_study.tracing import langfuse as tracing


def _flaky(failures: list[BaseException], result: str = "ok"):
    calls = []

    def fn() -> str:
        calls.append(1)
        if failures:
            raise failures.pop(0)
        return result

    return fn, calls


def test_with_retry_recovers_from_timeouts_and_5xx() -> None:
    fn, calls = _flaky([httpx.ReadTimeout("slow"), ApiError(status_code=503, body="busy")])
    slept: list[float] = []
    assert tracing.with_retry(fn, what="t", delays=(0.1, 0.2, 0.4), sleep=slept.append) == "ok"
    assert len(calls) == 3 and slept == [0.1, 0.2]


def test_with_retry_raises_after_the_last_attempt() -> None:
    fn, calls = _flaky([httpx.ConnectError("down")] * 5)
    with pytest.raises(httpx.ConnectError):
        tracing.with_retry(fn, what="t", delays=(0.0, 0.0), sleep=lambda _: None)
    assert len(calls) == 3


def test_with_retry_does_not_retry_client_errors() -> None:
    fn, calls = _flaky([ApiError(status_code=404, body="nope")])
    with pytest.raises(ApiError):
        tracing.with_retry(fn, what="t", delays=(0.0,), sleep=lambda _: None)
    assert len(calls) == 1


def test_awith_retry_survives_several_event_loops() -> None:
    """The manifest runs each entry in its own asyncio.run: the call must work in each."""
    for _ in range(3):
        fn, calls = _flaky([httpx.ReadTimeout("slow")])
        assert asyncio.run(tracing.awith_retry(fn, what="t", delays=(0.0,))) == "ok"
        assert len(calls) == 2


def test_preflight_fails_fast_when_langfuse_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    class Down:
        class api:  # noqa: N801
            class projects:  # noqa: N801
                @staticmethod
                def get():
                    raise httpx.ConnectError("refused")

    monkeypatch.setattr(tracing, "enabled", lambda: True)
    monkeypatch.setattr(tracing, "client", lambda: Down)
    with pytest.raises(tracing.LangfuseUnavailableError, match="unreachable"):
        tracing.preflight(delays=(0.0, 0.0))


def test_preflight_is_a_noop_without_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "enabled", lambda: False)
    tracing.preflight()
