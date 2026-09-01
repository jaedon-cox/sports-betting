"""Pro-rata pacing: the cap holds without it, the product does not."""

from __future__ import annotations

from datetime import UTC, datetime

from sbm.jobs.pacing import PaceGuard, paced_allowance
from sbm.odds.budget import OddsBudget
from sbm.odds.budget_store import InMemoryUsageStore


def _guard(used: int) -> PaceGuard:
    store = InMemoryUsageStore()
    if used:
        store.record("2026-07", used, endpoint="test", called_at=datetime(2026, 7, 1, tzinfo=UTC))
    return PaceGuard(budget=OddsBudget(store=store))


def test_allowance_is_the_doc_cadence_times_the_day() -> None:
    """15/day is 1 open snapshot (3) + 4 closing sweeps (12) — doc §2.5."""
    assert paced_allowance(datetime(2026, 7, 1, 12, tzinfo=UTC)) == 15
    assert paced_allowance(datetime(2026, 7, 31, 12, tzinfo=UTC)) == 465


def test_a_full_month_at_pace_stays_under_the_cap_with_headroom() -> None:
    """465 of 500 leaves the ~35 §2.5 reserves for doubleheaders and retries."""
    assert paced_allowance(datetime(2026, 7, 31, 12, tzinfo=UTC)) < 500


def test_day_one_affords_exactly_the_open_plus_four_sweeps() -> None:
    day_one = datetime(2026, 7, 1, 20, tzinfo=UTC)
    assert _guard(used=3).headroom(day_one) == 12   # open spent, 4 sweeps left
    assert _guard(used=15).allows(3, day_one) is False


def test_unspent_days_roll_forward() -> None:
    """A rained-out Tuesday's credits are what a Thursday twin bill needs."""
    later = datetime(2026, 7, 10, 20, tzinfo=UTC)
    assert _guard(used=15).headroom(later) == 135


def test_the_hard_cap_still_binds_when_a_looser_pace_would_allow() -> None:
    """At the default 15/day the pace is always the tighter of the two (465 < 500),
    so the cap check in `allows` only earns its place if `SBM_DAILY_ODDS_CREDITS`
    is raised. This is that case — and the cap must win, since it is the
    correctness constraint (CLAUDE.md rule 8) and the pace is only policy."""
    store = InMemoryUsageStore()
    store.record("2026-07", 499, endpoint="test", called_at=datetime(2026, 7, 1, tzinfo=UTC))
    guard = PaceGuard(budget=OddsBudget(store=store), daily_credits=20)
    end_of_month = datetime(2026, 7, 31, 20, tzinfo=UTC)
    assert guard.headroom(end_of_month) > 3        # pace says fine (620 allowed)
    assert guard.allows(3, end_of_month) is False  # cap says no (499 + 3 > 500)
