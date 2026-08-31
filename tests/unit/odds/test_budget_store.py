"""JsonlUsageStore must persist usage across separate process instances —
that's the whole point of not using an in-process counter (budget.py docstring)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sbm.odds.budget import UsageStore
from sbm.odds.budget_store import (
    JsonlUsageStore,
    PostgrestUsageStore,
    SupabaseUsageStore,
)


def test_jsonl_store_survives_a_fresh_instance(tmp_path: Path) -> None:
    path = tmp_path / "usage.jsonl"
    at = datetime(2026, 8, 29, tzinfo=UTC)

    first = JsonlUsageStore(path)
    first.record("2026-08", 3, endpoint="odds/mlb", called_at=at)
    first.record("2026-08", 6, endpoint="odds/mlb", called_at=at)

    # Simulate a brand-new CI runner reading the same persisted file.
    second = JsonlUsageStore(path)
    assert second.credits_used("2026-08") == 9
    assert second.credits_used("2026-09") == 0


def test_supabase_usage_store_delegates_to_injected_functions() -> None:
    inserted = []
    store = SupabaseUsageStore(
        insert=lambda table, row: inserted.append((table, row)),
        sum_credits=lambda table, month_key: 12,
    )
    at = datetime(2026, 8, 29, tzinfo=UTC)
    store.record("2026-08", 3, endpoint="odds/mlb", called_at=at)

    assert inserted == [
        (
            "odds_budget_usage",
            {
                "month_key": "2026-08",
                "credits": 3,
                "endpoint": "odds/mlb",
                "called_at_utc": at.isoformat(),
            },
        )
    ]
    assert store.credits_used("2026-08") == 12


class _FakePostgrest:
    """Stands in for `sbm.store.client.PostgrestClient` — no network.

    Mirrors only the two entry points `sbm.store.budget` uses.
    """

    def __init__(self, total: int = 0) -> None:
        self.inserted: list[tuple[str, list[dict]]] = []
        self.rpc_calls: list[tuple[str, dict]] = []
        self._total = total

    def insert(self, table: str, rows: list[dict]) -> list[dict]:
        self.inserted.append((table, rows))
        return rows

    def rpc(self, fn: str, params: dict) -> int:
        self.rpc_calls.append((fn, params))
        return self._total


def test_postgrest_store_reads_the_month_total_through_the_rpc() -> None:
    client = _FakePostgrest(total=447)
    assert PostgrestUsageStore(client).credits_used("2026-08") == 447
    assert client.rpc_calls == [("fn_odds_budget_month_total", {"p_month_key": "2026-08"})]


def test_postgrest_store_appends_one_ledger_row_per_charge() -> None:
    client = _FakePostgrest()
    store = PostgrestUsageStore(client)
    store.record(
        "2026-08", 3, endpoint="odds/mlb", called_at=datetime(2026, 8, 29, 23, 0, tzinfo=UTC)
    )
    (table, rows) = client.inserted[0]
    assert table == "odds_budget_usage"
    assert rows[0]["month_key"] == "2026-08"
    assert rows[0]["credits"] == 3


def test_postgrest_store_stamps_the_callers_instant_not_the_dbs() -> None:
    """A call near a month boundary must be timestamped into the same month
    it is billed to — see PostgrestUsageStore's docstring."""
    client = _FakePostgrest()
    at = datetime(2026, 8, 31, 23, 59, tzinfo=UTC)
    PostgrestUsageStore(client).record("2026-08", 3, endpoint="odds/mlb", called_at=at)
    (_table, rows) = client.inserted[0]
    assert rows[0]["called_at_utc"] == at.isoformat()


def test_postgrest_store_satisfies_the_usage_store_protocol() -> None:
    assert isinstance(PostgrestUsageStore(_FakePostgrest()), UsageStore)
