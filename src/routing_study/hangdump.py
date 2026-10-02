"""Hang diagnostics for long batch runs (tune_router, study runs).

- `dump(loop)`: every thread's stack (`faulthandler`) + every asyncio task of `loop` with
  its await stack, to stderr (or `stream`).
- `install_sigusr1()`: `kill -USR1 <pid>` dumps the same, live, without root (py-spy needs
  sudo on macOS).
- `Watchdog`: `beat()` on every finished unit of work; if none comes for `stall_after_s`
  (monotonic, so host sleep does not count), it dumps once per stall. It also reports host
  sleep: a wall-clock jump much larger than the monotonic one (macOS `time.monotonic` stops
  while the machine sleeps or hibernates), which looks exactly like a hang from outside.
"""

from __future__ import annotations

import asyncio
import faulthandler
import io
import signal
import sys
import time
from typing import TextIO

_loop: asyncio.AbstractEventLoop | None = None  # the loop SIGUSR1 reports on


def dump(
    loop: asyncio.AbstractEventLoop | None = None, stream: TextIO | None = None, why: str = ""
) -> None:
    out = stream or sys.stderr
    print(f"\n# ===== hang dump {time.strftime('%Y-%m-%dT%H:%M:%S')} {why}".rstrip(), file=out)
    try:
        fd = out.fileno()
    except (AttributeError, OSError, io.UnsupportedOperation):
        fd = None
    out.flush()
    if fd is not None:
        faulthandler.dump_traceback(file=fd, all_threads=True)
    else:  # an in-memory stream (tests): Python-level thread stacks
        import traceback

        for tid, frame in sys._current_frames().items():
            print(f"Thread {tid:#x}:", file=out)
            traceback.print_stack(frame, file=out)
    loop = loop or _loop
    if loop is not None and not loop.is_closed():
        tasks = asyncio.all_tasks(loop)
        print(f"# asyncio tasks: {len(tasks)}", file=out)
        for t in tasks:
            print(f"--- {t!r}", file=out)
            t.print_stack(file=out)
    print("# ===== end hang dump", file=out, flush=True)


def install_sigusr1(loop: asyncio.AbstractEventLoop | None = None) -> None:
    """SIGUSR1 -> `dump()` of the current loop (main thread only; idempotent)."""
    global _loop
    if loop is not None:
        _loop = loop
    signal.signal(signal.SIGUSR1, lambda *_: dump(why="(SIGUSR1)"))


class Watchdog:
    """Dumps when no `beat()` arrives for `stall_after_s`; 0 disables the stall dump."""

    def __init__(
        self,
        stall_after_s: float,
        *,
        check_every_s: float = 15.0,
        sleep_gap_s: float = 60.0,
        stream: TextIO | None = None,
    ) -> None:
        self.stall_after_s = stall_after_s
        self.check_every_s = check_every_s
        self.sleep_gap_s = sleep_gap_s
        self.stream = stream
        self.dumps = 0
        self.slept_s = 0.0
        self._last = time.monotonic()
        self._fired = False
        self._timer: asyncio.TimerHandle | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mono, self._wall = time.monotonic(), time.time()

    def beat(self) -> None:
        self._last = time.monotonic()
        self._fired = False

    def _tick(self) -> None:
        """A loop timer, not a task: no coroutine to cancel, and immune to a patched
        `asyncio.sleep` (tests replace it with a no-op)."""
        m, w = time.monotonic(), time.time()
        gap = (w - self._wall) - (m - self._mono)
        if gap > self.sleep_gap_s:
            self.slept_s += gap
            print(
                f"# watchdog: host was asleep ~{gap / 60:.1f} min (wall clock jumped; not a hang)",
                file=self.stream or sys.stderr,
                flush=True,
            )
        self._mono, self._wall = m, w
        idle = m - self._last
        if self.stall_after_s and idle >= self.stall_after_s and not self._fired:
            self._fired = True
            self.dumps += 1
            dump(self._loop, self.stream, f"(no progress for {idle:.0f}s)")
        if self._loop is not None and not self._loop.is_closed():
            self._timer = self._loop.call_later(self.check_every_s, self._tick)

    def start(self) -> Watchdog:
        """Start watching on the running loop (also the loop SIGUSR1 reports on)."""
        global _loop
        _loop = self._loop = asyncio.get_running_loop()
        self.beat()
        self._mono, self._wall = time.monotonic(), time.time()
        self._timer = self._loop.call_later(self.check_every_s, self._tick)
        return self

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._loop = None
