"""Spend ledger + hard budget caps per billing account.

- Every model call is appended to a JSONL ledger (`budget.ledger_path`, never rewritten):
  provider, model, tokens (incl. cache read/write), cost, wall time. Local models cost 0
  but are recorded too.
- Providers that report no cost (Bedrock) are priced from `budget.prices_path`
  (USD per 1M tokens; the file names its sources).
- `reserve()` runs BEFORE a call: cumulative spend + in-flight reservations + this call's
  upper-bound cost must stay within the account's cap, else `BudgetExceededError` (never
  retried). `settle()` replaces the reservation with the real cost.
- Multi-process safe: committed spend and every process's reservations are re-read under an
  exclusive file lock at each check (see `SpendLedger`).
"""

from __future__ import annotations

import fcntl
import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from routing_study.settings import Settings

# billing account per provider; providers without an account (ollama) are never capped
ACCOUNTS = {"bedrock": "aws", "openrouter": "openrouter"}


class BudgetExceededError(RuntimeError):
    """A call (or a run) would push an account past its cap. Aborts the run; never retried."""


@dataclass(frozen=True)
class Price:
    """USD per 1M tokens."""

    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0  # 5-minute TTL
    cache_write_1h: float | None = None

    def cost(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        cache_read: int = 0,
        cache_write: int = 0,
        cache_write_1h: int = 0,
    ) -> float:
        """`prompt_tokens` includes the cached and cache-written tokens (OpenAI convention)."""
        uncached = max(0, prompt_tokens - cache_read - cache_write - cache_write_1h)
        w1h = self.cache_write_1h if self.cache_write_1h is not None else 2 * self.input
        return (
            uncached * self.input
            + completion_tokens * self.output
            + cache_read * self.cache_read
            + cache_write * self.cache_write
            + cache_write_1h * w1h
        ) / 1e6


def load_prices(path: str | Path) -> dict[tuple[str, str], Price]:
    """`{provider: {model: {input, output, cache_read, cache_write[, cache_write_1h]}}}`;
    keys starting with `_` (e.g. `_source`) are notes."""
    p = Path(path)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out: dict[tuple[str, str], Price] = {}
    for provider, models in data.items():
        if provider.startswith("_") or not isinstance(models, dict):
            continue
        for model, row in models.items():
            if model.startswith("_"):
                continue
            fields = {k: v for k, v in row.items() if not k.startswith("_")}
            out[(provider, model)] = Price(**fields)
    return out


class Reservation(float):
    """The reserved upper bound (a float, for callers that add it up) + its entry id in the
    shared reservation file."""

    rid: str | None = None

    def __new__(cls, usd: float, rid: str | None = None) -> Reservation:
        obj = super().__new__(cls, usd)
        obj.rid = rid
        return obj


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # exists, owned by someone else
        return True
    return True


class SpendLedger:
    """Append-only JSONL ledger with per-account caps, safe across threads AND processes
    (tune_router workers, parallel runs share one file).

    Every check/reserve/settle holds an exclusive `fcntl.flock` on `<ledger>.lock`, re-reads
    the rows other processes committed since the last look (incremental, by file offset) and
    the in-flight reservations of every process (`<ledger>.reservations.json`: entries of dead
    processes are dropped), so two processes can never both spend the same headroom."""

    def __init__(self, path: str | Path, caps: dict[str, float]) -> None:
        self.path = Path(path)
        self.caps = caps
        self._lock = threading.Lock()
        self._offset = 0
        self.spent: dict[str, float] = {}
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.reservations_path = self.path.with_name(self.path.name + ".reservations.json")
        with self._locked():
            pass  # loads the committed totals

    # ------------------------------------------------------------ file state (lock held)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a") as fh:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                try:
                    self._refresh()
                    yield
                finally:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def _refresh(self) -> None:
        """Add the rows appended since `_offset` (from any process) to `spent`."""
        if not self.path.exists():
            self._offset, self.spent = 0, {}
            return
        with self.path.open("rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            if size < self._offset:  # truncated / replaced: start over
                self._offset, self.spent = 0, {}
            fh.seek(self._offset)
            chunk = fh.read()
        end = chunk.rfind(b"\n") + 1  # complete lines only
        for line in chunk[:end].decode("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            acct = ACCOUNTS.get(row.get("provider", ""))
            if acct:
                self.spent[acct] = self.spent.get(acct, 0.0) + float(row.get("cost_usd") or 0)
        self._offset += end

    def _read_reservations(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.reservations_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return {k: v for k, v in data.items() if _pid_alive(int(v.get("pid", 0)))}

    def _write_reservations(self, data: dict[str, dict[str, Any]]) -> None:
        tmp = self.reservations_path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self.reservations_path)

    def _pending(self, acct: str, data: dict[str, dict[str, Any]]) -> float:
        return sum(float(v["usd"]) for v in data.values() if v.get("acct") == acct)

    def _check(self, acct: str, projected: float, what: str, pending: float) -> None:
        cap = self.caps.get(acct)
        if cap is None:
            return
        used = self.spent.get(acct, 0.0) + pending
        if used + projected > cap:
            raise BudgetExceededError(
                f"{acct} budget: spent ${used:.4f} + {what} ${projected:.4f} "
                f"> cap ${cap:.2f} (ledger {self.path})"
            )

    # ------------------------------------------------------------ API

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def check(self, provider: str, projected_usd: float, what: str = "run") -> None:
        """Raise when spent + in-flight (all processes) + `projected_usd` would exceed the cap."""
        acct = ACCOUNTS.get(provider)
        if acct is None:
            return
        with self._locked():
            pending = self._pending(acct, self._read_reservations())
            self._check(acct, projected_usd, what, pending)

    def reserve(self, provider: str, upper_bound_usd: float) -> Reservation:
        acct = ACCOUNTS.get(provider)
        if acct is None:
            return Reservation(0.0)
        with self._locked():
            data = self._read_reservations()
            self._check(acct, upper_bound_usd, "this call (upper bound)", self._pending(acct, data))
            rid = f"{os.getpid()}-{uuid.uuid4().hex}"
            data[rid] = {"acct": acct, "usd": upper_bound_usd, "pid": os.getpid()}
            self._write_reservations(data)
        return Reservation(upper_bound_usd, rid)

    def settle(self, provider: str, reserved: float, record: dict[str, Any] | None) -> None:
        """Release a reservation and, when the call returned, append its real usage."""
        acct = ACCOUNTS.get(provider)
        with self._locked():
            if acct is not None and reserved:
                data = self._read_reservations()
                rid = getattr(reserved, "rid", None)
                if rid is None:  # a bare float: this process's first entry of that amount
                    rid = next(
                        (
                            k
                            for k, v in data.items()
                            if v.get("pid") == os.getpid()
                            and v.get("acct") == acct
                            and float(v["usd"]) == float(reserved)
                        ),
                        None,
                    )
                if data.pop(rid, None) is not None:
                    self._write_reservations(data)
            if record is None:
                return
            row = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "provider": provider}
            row.update(record)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._refresh()


_ledgers: dict[str, SpendLedger] = {}
_prices: dict[str, dict[tuple[str, str], Price]] = {}


def ledger_for(settings: Settings) -> SpendLedger:
    """One ledger per file per process (caps from the latest settings)."""
    b = settings.budget
    key = str(Path(b.ledger_path).resolve())
    caps = {"aws": b.aws_usd_cap, "openrouter": b.openrouter_usd_cap}
    led = _ledgers.get(key)
    if led is None:
        led = _ledgers[key] = SpendLedger(b.ledger_path, caps)
    led.caps = caps
    return led


def prices_for(settings: Settings) -> dict[tuple[str, str], Price]:
    path = settings.budget.prices_path
    if path not in _prices:
        _prices[path] = load_prices(path)
    return _prices[path]


class CallMeter:
    """reserve -> call -> settle around one model call (context manager)."""

    def __init__(
        self, ledger: SpendLedger | None, provider: str, model: str, upper_bound_usd: float
    ) -> None:
        self.ledger, self.provider, self.model = ledger, provider, model
        self.upper = upper_bound_usd
        self.record: dict[str, Any] | None = None

    def __enter__(self) -> CallMeter:
        self.reserved = self.ledger.reserve(self.provider, self.upper) if self.ledger else 0.0
        self.t0 = time.perf_counter()
        return self

    def done(self, usage: dict[str, Any], **extra: Any) -> None:
        keys = ("cost_usd", "prompt_tokens", "completion_tokens", "cache_read", "cache_write")
        self.record = {
            "model": self.model,
            **{k: usage.get(k, 0) for k in keys},
            "served_model": usage.get("served_model"),
            "wall_ms": round((time.perf_counter() - self.t0) * 1000, 1),
            **extra,
        }

    def __exit__(self, *exc: object) -> None:
        if self.ledger is not None:
            self.ledger.settle(self.provider, self.reserved, self.record)


def summarize(rows: list[dict[str, Any]]) -> str:
    """Spend by provider / model, with caps, for `study budget`."""
    by: dict[tuple[str, str], dict[str, float]] = {}
    for r in rows:
        k = (r.get("provider", "?"), r.get("model", "?"))
        agg = by.setdefault(k, {"calls": 0, "cost": 0.0, "in": 0, "out": 0, "cr": 0, "cw": 0})
        agg["calls"] += 1
        agg["cost"] += float(r.get("cost_usd") or 0)
        agg["in"] += int(r.get("prompt_tokens") or 0)
        agg["out"] += int(r.get("completion_tokens") or 0)
        agg["cr"] += int(r.get("cache_read") or 0)
        agg["cw"] += int(r.get("cache_write") or 0)
    head = (
        f"{'provider':<11}{'model':<50}{'calls':>7}{'prompt':>10}{'compl':>8}"
        f"{'c.read':>9}{'c.write':>9}{'USD':>11}"
    )
    lines = [head, "-" * len(head)]
    for (prov, model), a in sorted(by.items()):
        lines.append(
            f"{prov:<11}{model[:49]:<50}{a['calls']:>7.0f}{a['in']:>10.0f}{a['out']:>8.0f}"
            f"{a['cr']:>9.0f}{a['cw']:>9.0f}{a['cost']:>11.4f}"
        )
    return "\n".join(lines)
