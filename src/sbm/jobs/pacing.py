"""Pro-rata pacing on top of the hard monthly Odds API cap.

`odds/budget.py` already refuses to exceed 500 credits in a month — that is the
correctness gate (CLAUDE.md rule 8). This module answers a different question
it deliberately does not: *should* a discretionary call be made now, given that
the month has to last 30 more days. Without pacing, a run of doubleheader-heavy
days early in the month spends the allowance and the last week of the month
prices nothing at all — the cap holds and the product silently stops working.

Backend doc §2.5's cadence is 15 credits/day (1 slate-wide open snapshot at 3,
plus up to 4 closing sweeps at 3 each). So the allowance through UTC day D is
`15 * D`: 465 by the end of a 31-day month, leaving ~35 of the 500 as the
doc's stated headroom "for doubleheaders and retries". Unspent days roll
forward, which is the behaviour you want — a rained-out Tuesday's credits are
exactly what a twin bill on Thursday needs.

This reads only `credits_used(month)`, which `OddsBudget` already exposes, so
it needs no new DB function and no per-day ledger query.

Job A's open snapshot is NOT paced — it is the one guaranteed daily call and
the anchor every pick's `bet_prob` is priced from. Only Job E's closing sweeps
are discretionary, and skipping one is the documented precision-for-budget
tradeoff (§2.5), not an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sbm.jobs.config import DEFAULT_DAILY_ODDS_CREDITS
from sbm.odds.budget import OddsBudget, month_key


def paced_allowance(at: datetime, *, daily_credits: int = DEFAULT_DAILY_ODDS_CREDITS) -> int:
    """Cumulative credits this month's spend may reach by the end of `at`'s day.

    The UTC day-of-month, matching `budget.month_key`'s UTC month bucket — The
    Odds API resets on its own cycle, not on the ET slate calendar.
    """
    return daily_credits * at.astimezone(UTC).day


@dataclass(frozen=True, slots=True)
class PaceGuard:
    """Whether a discretionary priced call fits this month's running pace."""

    budget: OddsBudget
    daily_credits: int = DEFAULT_DAILY_ODDS_CREDITS

    def headroom(self, at: datetime) -> int:
        """Credits still available under the pace (never below 0).

        Can be smaller than `OddsBudget.remaining()` — that is the point.
        """
        used = self.budget.store.credits_used(month_key(at))
        return max(0, paced_allowance(at, daily_credits=self.daily_credits) - used)

    def allows(self, cost: int, at: datetime) -> bool:
        """Does a `cost`-credit call fit both the pace and the hard cap?"""
        return cost <= self.headroom(at) and cost <= self.budget.remaining(at=at)
