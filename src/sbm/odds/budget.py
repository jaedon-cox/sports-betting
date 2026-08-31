"""Enforces The Odds API's 500-req/month free-tier cap before any credit is spent.

Backend doc §2.5: cost is `markets x regions` per call (3 markets x 1 region = 3
credits), and the whole system's cadence (1 open snapshot/day + up to 4
closing-window sweeps/day from ~6 cron triggers) is budgeted at ~450/month
against the 500 cap. Every odds call site must route through `OddsBudget.charge`
FIRST — this module has no HTTP client and knows nothing about The Odds API's
wire format, so it is trivially testable and cannot itself over-spend.

Usage must persist across ephemeral CI runs: each GitHub Actions job is a fresh
filesystem, so the ledger lives behind the `UsageStore` protocol rather than an
in-process counter. See `odds/budget_store.py` for concrete stores.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

MONTHLY_CREDIT_CAP = 500
"""The Odds API free tier (backend doc §1.1, §2.5)."""


def credit_cost(markets: int, regions: int) -> int:
    """The Odds API's billing formula: `markets x regions` per call (doc §2.5)."""
    return markets * regions


class BudgetExceeded(RuntimeError):
    """Raised instead of spending credits past the monthly cap.

    Refusing the call is the correctness requirement (spawn brief: "REFUSE the
    call when exhausted rather than overspending") — a silent overspend breaks
    every other consumer of the shared 500/month allowance for the rest of the
    cycle.
    """

    def __init__(self, requested: int, used: int, cap: int, month_key: str) -> None:
        self.requested = requested
        self.used = used
        self.cap = cap
        self.month_key = month_key
        super().__init__(
            f"refusing odds call for {month_key}: {requested} credits would bring "
            f"usage to {used + requested}/{cap}"
        )


@runtime_checkable
class UsageStore(Protocol):
    """Durable, insert-only ledger of credits spent per calendar month.

    `credits_used` must reflect every prior `record` call for that month,
    including ones from other processes/CI runs — this is what makes the
    budget survive across ~6 independent scheduled invocations per day.
    """

    def credits_used(self, month_key: str) -> int:
        """Sum of credits recorded for `month_key` (UTC, format `YYYY-MM`)."""
        ...

    def record(self, month_key: str, credits: int, *, endpoint: str, called_at: datetime) -> None:
        """Append one spend event. Never mutate or aggregate in place."""
        ...


def month_key(at: datetime) -> str:
    """The UTC calendar-month bucket a call's usage is billed against."""
    return at.astimezone(UTC).strftime("%Y-%m")


@dataclass(frozen=True, slots=True)
class OddsBudget:
    """Gate in front of every Odds API call site.

    Credits are debited (`store.record`) BEFORE the HTTP request is made, not
    after a successful response — this guarantees the cap is never exceeded
    even if two cron-triggered jobs race, or the process crashes mid-call. The
    conservative cost is that a request which fails after being charged still
    consumes its reserved credits; that trade favors "never overspend" over
    "never waste," which matches the brief.
    """

    store: UsageStore
    cap: int = MONTHLY_CREDIT_CAP

    def remaining(self, *, at: datetime | None = None) -> int:
        at = at or datetime.now(UTC)
        return self.cap - self.store.credits_used(month_key(at))

    def charge(
        self,
        *,
        markets: int,
        regions: int,
        endpoint: str,
        at: datetime | None = None,
    ) -> int:
        """Reserve credits for an imminent call, or raise `BudgetExceeded`.

        Call this before making the HTTP request. Returns the credit cost so
        callers can log it.
        """
        at = at or datetime.now(UTC)
        cost = credit_cost(markets, regions)
        key = month_key(at)
        used = self.store.credits_used(key)
        if used + cost > self.cap:
            raise BudgetExceeded(cost, used, self.cap, key)
        self.store.record(key, cost, endpoint=endpoint, called_at=at)
        return cost
