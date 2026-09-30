"""Spend ledger + hard budget caps per billing account.

- Every model call is appended to a JSONL ledger (`budget.ledger_path`, never rewritten):
  provider, model, tokens (incl. cache read/write), cost, wall time. Local models cost 0
  but are recorded too.
- Providers that report no cost (Bedrock) are priced from `budget.prices_path`
  (USD per 1M tokens; the file names its sources).
- `reserve()` runs BEFORE a call: cumulative spend + in-flight reservations + this call's
  upper-bound cost must stay within the account's cap, else `BudgetExceededError` (never
  retried). `settle()` replaces the reservation with the real cost.
"""

from __future__ import annotations

import json
import threading
import time
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


class SpendLedger:
    """Append-only JSONL ledger with per-account caps. Thread-safe (Bedrock calls run in
    worker threads); totals are loaded from the file once, then kept in memory."""

    def __init__(self, path: str | Path, caps: dict[str, float]) -> None:
        self.path = Path(path)
        self.caps = caps
        self._lock = threading.Lock()
        self._pending: dict[str, float] = {}
        self.spent: dict[str, float] = {}
        for row in self.rows():
            acct = ACCOUNTS.get(row.get("provider", ""))
            if acct:
                self.spent[acct] = self.spent.get(acct, 0.0) + float(row.get("cost_usd") or 0)

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def check(self, provider: str, projected_usd: float, what: str = "run") -> None:
        """Raise when spent + in-flight + `projected_usd` would exceed the account cap."""
        acct = ACCOUNTS.get(provider)
        if acct is None:
            return
        with self._lock:
            self._check(acct, projected_usd, what)

    def _check(self, acct: str, projected: float, what: str) -> None:
        cap = self.caps.get(acct)
        if cap is None:
            return
        used = self.spent.get(acct, 0.0) + self._pending.get(acct, 0.0)
        if used + projected > cap:
            raise BudgetExceededError(
                f"{acct} budget: spent ${used:.4f} + {what} ${projected:.4f} "
                f"> cap ${cap:.2f} (ledger {self.path})"
            )

    def reserve(self, provider: str, upper_bound_usd: float) -> float:
        acct = ACCOUNTS.get(provider)
        if acct is None:
            return 0.0
        with self._lock:
            self._check(acct, upper_bound_usd, "this call (upper bound)")
            self._pending[acct] = self._pending.get(acct, 0.0) + upper_bound_usd
        return upper_bound_usd

    def settle(self, provider: str, reserved: float, record: dict[str, Any] | None) -> None:
        """Release a reservation and, when the call returned, append its real usage."""
        acct = ACCOUNTS.get(provider)
        with self._lock:
            if acct is not None:
                self._pending[acct] = max(0.0, self._pending.get(acct, 0.0) - reserved)
            if record is None:
                return
            row = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "provider": provider}
            row.update(record)
            if acct is not None:
                self.spent[acct] = self.spent.get(acct, 0.0) + float(row.get("cost_usd") or 0)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


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
