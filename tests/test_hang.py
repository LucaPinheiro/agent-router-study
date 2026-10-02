"""No await of a model call can block a batch forever, and a stall is diagnosable.

Fakes for the conditions a long local run meets: a server that accepts the request and never
answers (stopped runner / dead keep-alive socket), a caller cancelled mid-call, a spend-ledger
lock held by another process, and a run that makes no progress or whose host slept.
"""

from __future__ import annotations

import asyncio
import fcntl
import io
import os
import signal

import pytest

from routing_study import hangdump
from routing_study.budget import SpendLedger
from routing_study.llm import CallDeadlineError, call_with_retry, provider_semaphore
from routing_study.settings import Settings


def _settings(**kw) -> Settings:
    base = {"http_retries": 1, "local_call_deadline_s": 0.05, "call_deadline_s": 0.05}
    return Settings(_env_file=None, **(base | kw))


async def _never() -> str:
    await asyncio.Event().wait()  # accepted, never answered
    return "unreachable"


async def test_silent_server_hits_the_deadline_and_frees_the_slot():
    s = _settings()
    calls = 0

    async def silent() -> str:
        nonlocal calls
        calls += 1
        return await _never()

    with pytest.raises(CallDeadlineError):
        await call_with_retry(silent, model="qwen3:8b", settings=s, provider="ollama")
    assert calls == s.http_retries + 1  # a deadline hit is retried like a transport timeout
    sem = provider_semaphore("ollama", s.ollama_num_parallel)
    assert sem._value == s.ollama_num_parallel  # released: the next case is not blocked

    async def ok() -> str:
        return "ok"

    got = await asyncio.wait_for(
        call_with_retry(ok, model="qwen3:8b", settings=s, provider="ollama"), 1.0
    )
    assert got == "ok"


async def test_deadline_applies_to_api_calls_too():
    with pytest.raises(CallDeadlineError):
        await call_with_retry(_never, model="a/b", settings=_settings(http_retries=0))


async def test_cancelled_caller_releases_the_provider_slot():
    s = _settings(local_call_deadline_s=0)  # disabled: the caller cancels instead
    task = asyncio.create_task(call_with_retry(_never, model="m", settings=s, provider="ollama"))
    await asyncio.sleep(0.01)
    assert provider_semaphore("ollama", 1)._value == 0  # held while in flight
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider_semaphore("ollama", 1)._value == 1


async def test_exception_inside_the_guarded_section_releases_the_slot():
    async def boom() -> None:
        raise ValueError("parse")  # not retryable

    with pytest.raises(ValueError):
        await call_with_retry(boom, model="m", settings=_settings(), provider="ollama")
    assert provider_semaphore("ollama", 1)._value == 1


def test_ledger_lock_held_elsewhere_times_out(tmp_path):
    led = SpendLedger(tmp_path / "l.jsonl", {"aws": 1.0}, lock_timeout_s=0.1)
    with open(led.lock_path, "a") as other:  # another open file description = another holder
        fcntl.flock(other.fileno(), fcntl.LOCK_EX)
        with pytest.raises(TimeoutError, match="lock"):
            led.reserve("bedrock", 0.01)
        fcntl.flock(other.fileno(), fcntl.LOCK_UN)
    led.settle("bedrock", led.reserve("bedrock", 0.01), None)  # free again


async def test_watchdog_dumps_the_stuck_task_once():
    out = io.StringIO()
    wd = hangdump.Watchdog(0.05, check_every_s=0.02, stream=out).start()

    async def stuck_case() -> None:
        await asyncio.Event().wait()

    t = asyncio.create_task(stuck_case(), name="case-1")
    await asyncio.sleep(0.2)
    wd.stop()
    t.cancel()
    text = out.getvalue()
    assert wd.dumps == 1 and "no progress" in text
    assert "case-1" in text and "stuck_case" in text  # the awaiting coroutine's stack
    assert "Thread" in text


async def test_watchdog_reports_host_sleep_not_a_hang(monkeypatch):
    out = io.StringIO()
    real = hangdump.time.time
    jump = {"s": 0.0}
    monkeypatch.setattr(hangdump.time, "time", lambda: real() + jump["s"])
    wd = hangdump.Watchdog(0, check_every_s=0.02, sleep_gap_s=60, stream=out).start()
    await asyncio.sleep(0.03)
    jump["s"] = 6 * 3600  # wall clock jumps 6 h, monotonic does not (macOS sleep)
    await asyncio.sleep(0.05)
    wd.stop()
    assert "asleep" in out.getvalue() and wd.slept_s > 3600 and wd.dumps == 0


async def test_sigusr1_dumps_live_tasks(capfd):
    old = signal.getsignal(signal.SIGUSR1)
    hangdump.install_sigusr1(asyncio.get_running_loop())
    try:

        async def waiting_on_ollama() -> None:
            await asyncio.Event().wait()

        t = asyncio.create_task(waiting_on_ollama())
        await asyncio.sleep(0)
        os.kill(os.getpid(), signal.SIGUSR1)
        await asyncio.sleep(0.05)
        t.cancel()
    finally:
        signal.signal(signal.SIGUSR1, old)
    err = capfd.readouterr().err
    assert "(SIGUSR1)" in err and "waiting_on_ollama" in err
