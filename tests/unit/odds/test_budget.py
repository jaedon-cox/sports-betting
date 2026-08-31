"""odds/budget.py must refuse a call rather than let usage exceed the cap."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sbm.odds.budget import BudgetExceeded, OddsBudget, credit_cost, month_key
from sbm.odds.budget_store import InMemoryUsageStore


def test_credit_cost_is_markets_times_regions() -> None:
    assert credit_cost(markets=3, regions=1) == 3
    assert credit_cost(markets=3, regions=2) == 6


def test_month_key_buckets_by_utc_calendar_month() -> None:
    assert month_key(datetime(2026, 8, 29, 23, 0, tzinfo=UTC)) == "2026-08"
    assert month_key(datetime(2026, 9, 1, 0, 0, tzinfo=UTC)) == "2026-09"


def test_charge_records_usage_and_returns_cost() -> None:
    budget = OddsBudget(store=InMemoryUsageStore(), cap=10)
    at = datetime(2026, 8, 29, tzinfo=UTC)
    cost = budget.charge(markets=3, regions=1, endpoint="odds/mlb", at=at)
    assert cost == 3
    assert budget.remaining(at=at) == 7


def test_charge_refuses_rather_than_overspend() -> None:
    budget = OddsBudget(store=InMemoryUsageStore(), cap=5)
    at = datetime(2026, 8, 29, tzinfo=UTC)
    budget.charge(markets=3, regions=1, endpoint="odds/mlb", at=at)
    with pytest.raises(BudgetExceeded):
        budget.charge(markets=3, regions=1, endpoint="odds/mlb", at=at)
    # The refused call must not have been recorded.
    assert budget.remaining(at=at) == 2


def test_usage_isolated_per_calendar_month() -> None:
    store = InMemoryUsageStore()
    budget = OddsBudget(store=store, cap=10)
    budget.charge(markets=9, regions=1, endpoint="odds/mlb", at=datetime(2026, 8, 31, tzinfo=UTC))
    # New month resets the effective allowance even though the store is shared.
    assert budget.remaining(at=datetime(2026, 9, 1, tzinfo=UTC)) == 10


def test_realistic_monthly_cadence_stays_under_cap() -> None:
    """Backend doc §2.5: 1 open snapshot/day + up to 4 closing sweeps/day,
    3 markets x 1 region each, ~30 days -> ~450/500."""
    store = InMemoryUsageStore()
    budget = OddsBudget(store=store)
    at = datetime(2026, 8, 1, tzinfo=UTC)
    total = 0
    for _day in range(30):
        for _call in range(5):  # 1 open + up to 4 closing sweeps
            total += budget.charge(markets=3, regions=1, endpoint="odds/mlb", at=at)
    assert total == 450
    assert budget.remaining(at=at) == 50
