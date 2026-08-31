"""Concrete `UsageStore` implementations for `odds/budget.py`.

`InMemoryUsageStore` is for tests. `JsonlUsageStore` is a local append-only
fallback that works without any external service. Neither is the production
backend: GitHub Actions runners are ephemeral, so credits spent by one cron
invocation must be visible to the next, which a local file cannot guarantee
across separate jobs.

**The production backend is `PostgrestUsageStore`** — `db` has since shipped
`odds_budget_usage` (db/migrations/008) plus `sbm.store.budget`, so the
durable path is now wired rather than pending. `SupabaseUsageStore` is kept
as the injected-callables variant: it predates 008 and stays useful for
tests and for any non-PostgREST backend, but jobs should use
`PostgrestUsageStore`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sbm.store.budget import get_month_credits_used, record_odds_usage
from sbm.store.client import PostgrestClient


@dataclass
class InMemoryUsageStore:
    """Process-local ledger. Only useful for tests — resets every run."""

    _events: list[tuple[str, int]] = field(default_factory=list)

    def credits_used(self, month_key: str) -> int:
        return sum(credits for key, credits in self._events if key == month_key)

    def record(self, month_key: str, credits: int, *, endpoint: str, called_at: datetime) -> None:
        del endpoint, called_at  # not needed for the in-memory ledger
        self._events.append((month_key, credits))


@dataclass
class JsonlUsageStore:
    """Append-only JSONL ledger on disk.

    Each `record` call appends one line; `credits_used` re-reads and sums.
    Safe for a single machine's sequential jobs, NOT safe for concurrent
    writers on separate machines (no locking) — that gap is exactly why
    production uses `PostgrestUsageStore`, where the DB serializes writes.
    """

    path: Path

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def credits_used(self, month_key: str) -> int:
        return sum(credits for key, credits in self._read() if key == month_key)

    def record(self, month_key: str, credits: int, *, endpoint: str, called_at: datetime) -> None:
        row = {
            "month_key": month_key,
            "credits": credits,
            "endpoint": endpoint,
            "called_at": called_at.isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    def _read(self) -> list[tuple[str, int]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            out.append((row["month_key"], int(row["credits"])))
        return out


class UsageRowWriter(Protocol):
    """Generic `(table, row)` insert that `SupabaseUsageStore` writes through.

    Kept for backends that expose a table-generic writer. `db`'s actual
    PostgREST API is not one of those — it takes no `table` argument — which
    is why `PostgrestUsageStore` calls it directly rather than adapting it
    to this shape.
    """

    def __call__(self, table: str, row: dict) -> None: ...


@dataclass
class SupabaseUsageStore:
    """Generic durable backend over injected callables: insert-only
    `odds_budget_usage(month_key, credits, endpoint, called_at_utc)` rows,
    summed per month.

    Prefer `PostgrestUsageStore` in production — it calls `db`'s shipped
    functions directly instead of routing through a generic `(table, row)`
    writer whose `table` argument the real API doesn't take.
    """

    insert: UsageRowWriter
    sum_credits: SumCreditsFn
    table: str = "odds_budget_usage"

    def credits_used(self, month_key: str) -> int:
        return self.sum_credits(self.table, month_key)

    def record(self, month_key: str, credits: int, *, endpoint: str, called_at: datetime) -> None:
        self.insert(
            self.table,
            {
                "month_key": month_key,
                "credits": credits,
                "endpoint": endpoint,
                "called_at_utc": called_at.isoformat(),
            },
        )


class SumCreditsFn(Protocol):
    def __call__(self, table: str, month_key: str) -> int: ...


@dataclass
class PostgrestUsageStore:
    """Production `UsageStore`: `db`'s `odds_budget_usage` ledger over PostgREST.

    This is what makes the cap real. `budget.py` charges *before* each HTTP
    call precisely so a crash mid-request cannot leave credits unaccounted —
    which only holds if the ledger outlives the runner, and on GitHub Actions
    nothing local does (db/migrations/008's own header makes the same point).

    `called_at` is always passed through rather than left to the column's
    `DEFAULT now()`: `budget.py` derives `month_key` from the same instant, so
    letting the DB stamp its own would let a call near a month boundary be
    billed to one month and timestamped into the other.
    """

    client: PostgrestClient

    def credits_used(self, month_key: str) -> int:
        return get_month_credits_used(self.client, month_key)

    def record(self, month_key: str, credits: int, *, endpoint: str, called_at: datetime) -> None:
        record_odds_usage(
            self.client,
            month_key=month_key,
            credits=credits,
            endpoint=endpoint,
            called_at_utc=called_at,
        )
