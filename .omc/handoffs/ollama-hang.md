# Ollama "deadlock" in tune_router (e6b P0+P5) — 2026-10-01

## Verdict
There was **no client-side deadlock**. The Mac hit **Low Power Sleep at 1% battery** (caffeinate
cannot prevent it) and hibernated for 6.2 h; the run resumed on wake and was progressing normally
when it was killed as "hung".

## Evidence
- `pmset -g log`: `2026-10-01 05:42:32 Sleep — Entering Sleep state due to 'Low Power Sleep'
  ... Using Batt (Charge:1%) 22309 secs`; `11:54:21 Wake from Hibernate ... Using AC (Charge:8%)`.
  caffeinate (pid 40476) held PreventSystemSleep the whole time, so the sleep was forced by the
  low battery.
- `results/spend_ledger.jsonl`: last P0+P5 call before the gap at 08:42:30Z (05:42:30 local, 2 s
  before sleep). The next row is at 14:54:32Z (11:54:32 local, 11 s after wake) with
  `wall_ms: 52008` — the call in flight at sleep; `perf_counter`/`monotonic` stop during macOS
  sleep, so 6.2 h of wall time measured 52 s. Then 37 more P0+P5 calls (14:54:32–14:58:19Z,
  same skill ~1340/~200 tok + tool ~680/~24 tok pattern) until the process was killed at
  14:58:21Z.
- The `sample` taken at 11:57:42 (main thread in kevent, 9 idle pool threads, 2 ESTABLISHED
  sockets to :11434) is the normal state of a concurrency-1 asyncio client waiting on a ~10 s
  Ollama reply. tune_router printed only once per grid point (~1 h per point on full dev), so
  nothing showed it was alive.
- `lsof results/spend_ledger.jsonl.lock`: no holders.
- Fault injection (new code): `kill -STOP` of the Ollama runner for 150 s mid-call during an
  uncached P0+P5 run (`--set strategies.llm_local.temperature=0.013`, subset 6). SIGUSR1 at +30 s
  dumped all tasks (the case awaiting `RunnableParallel.ainvoke` -> `_agenerate_with_cache`);
  the stall watchdog dumped at +65 s; the attempt timed out and was retried (new task ids in the
  second dump; Ollama replaced the stopped runner), and the run finished 6/6 with 0 errors.

## Changes (defensive, plus diagnostics so this is never misread again)
- `src/routing_study/hangdump.py`: `dump()` (faulthandler thread stacks + `asyncio.all_tasks`
  with stacks), `install_sigusr1()` (`kill -USR1 <pid>`, no root), `Watchdog` (loop timer: dumps
  once if no case finishes for N s, monotonic so sleep does not count; prints
  "host was asleep ~X min" when the wall clock jumps past the monotonic clock).
- `scripts/analysis/tune_router.py`: `--stall-dump-s` (default 600), `--progress N` (stderr line
  every N cases, default 10), SIGUSR1 handler installed.
- `src/routing_study/llm.py`: `call_with_retry` bounds every attempt with `asyncio.wait_for`
  (`local_call_deadline_s`=120 for Ollama, `call_deadline_s`=90 for APIs; 0 disables);
  a hit raises `CallDeadlineError` and is retried like a transport timeout. The provider
  semaphore was already `async with` (released on error/cancel); tests now pin that.
- `src/routing_study/budget.py`: ledger `flock` is polled with `LOCK_NB` and raises
  `TimeoutError` after `lock_timeout_s` (60 s) instead of blocking the event-loop thread forever.
- `tests/test_hang.py`: silent server -> deadline + slot freed; API deadline; cancelled caller and
  in-section exception free the slot; ledger lock held elsewhere times out; watchdog dumps the
  stuck task; host-sleep detection; SIGUSR1 dump.

## Operational advice
Run long local jobs on AC power: caffeinate cannot stop low-battery sleep. After a gap, check
`pmset -g log | grep -E "Sleep|Wake"` and the ledger timestamps before assuming a hang.
