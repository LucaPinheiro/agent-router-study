"""F3: the spend ledger is shared by concurrent processes (tune_router workers, parallel
runs): committed spend is re-read and reservations are visible across processes, under an
exclusive file lock, so two processes cannot both spend the same headroom."""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pytest

from routing_study.budget import BudgetExceededError, CallMeter, SpendLedger

CAP = {"aws": 0.10, "openrouter": 1.0}


def _grab(path: str, start, n: int, out) -> None:  # noqa: ANN001 (mp primitives)
    """Reserve 0.03 up to `n` times and HOLD the reservations (calls still in flight)."""
    led = SpendLedger(path, CAP)
    start.wait()
    got = 0
    for _ in range(n):
        try:
            led.reserve("bedrock", 0.03)
            got += 1
        except BudgetExceededError:
            pass
    out.put(got)
    start.wait()  # keep the process (and its reservations) alive until both have counted


def _spend(path: str, usd: float) -> None:
    led = SpendLedger(path, CAP)
    with CallMeter(led, "bedrock", "m", 0.0) as meter:
        meter.done({"cost_usd": usd})


def _ctx() -> mp.context.SpawnContext:
    return mp.get_context("spawn")


def test_two_processes_cannot_both_reserve_the_same_headroom(tmp_path: Path) -> None:
    ctx = _ctx()
    path = str(tmp_path / "ledger.jsonl")
    start, out = ctx.Barrier(2), ctx.Queue()
    procs = [ctx.Process(target=_grab, args=(path, start, 4, out)) for _ in range(2)]
    for p in procs:
        p.start()
    got = [out.get(timeout=60) for _ in procs]
    for p in procs:
        p.join(timeout=60)
        assert p.exitcode == 0
    assert sum(got) == 3  # floor(0.10 / 0.03): never 6 (each process alone would take 3)


def test_spend_committed_by_another_process_is_seen_at_the_next_check(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    mine = SpendLedger(path, CAP)  # loaded before the other process spends
    mine.reserve("bedrock", 0.05)
    mine.settle("bedrock", 0.05, None)
    p = _ctx().Process(target=_spend, args=(str(path), 0.08))
    p.start()
    p.join(timeout=60)
    assert p.exitcode == 0
    with pytest.raises(BudgetExceededError, match="aws budget"):
        mine.reserve("bedrock", 0.03)
    with pytest.raises(BudgetExceededError):
        mine.check("bedrock", 0.03)
    assert mine.spent["aws"] == pytest.approx(0.08)


def test_reservations_of_a_dead_process_are_released(tmp_path: Path) -> None:
    ctx = _ctx()
    path = str(tmp_path / "ledger.jsonl")
    p = ctx.Process(target=_reserve_and_die, args=(path,))
    p.start()
    p.join(timeout=60)
    assert p.exitcode == 0
    led = SpendLedger(path, CAP)
    led.reserve("bedrock", 0.09)  # the dead process's 0.09 no longer blocks the cap


def _reserve_and_die(path: str) -> None:
    SpendLedger(path, CAP).reserve("bedrock", 0.09)  # never settled: the process exits
