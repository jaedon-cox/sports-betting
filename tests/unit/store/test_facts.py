"""SettlementRow's two guards.

clv_pct is derived from bet_prob and closing_prob, and pick_settlements is
insert-once, so a row storing the derived number without its inputs can never
be audited or repaired. Migration 016 is what actually enforces that; these
guards fail earlier and name the field.

Neither state is reachable from Job F today — its _clv() returns None whenever
a leg is missing. These tests pin the boundary contract for the next writer,
NOT a live bug. (An earlier version of this docstring called it the same defect
class as the picks.devig_method gap. That was wrong: 013 repaired a gap that
made every priced pick unpublishable, and this one has no live path to it.)
"""

from __future__ import annotations

import pytest

from sbm.store.facts import SettlementRow, write_settlements


class _FakePostgrest:
    """Stands in for `sbm.store.client.PostgrestClient` — no network."""

    def __init__(self) -> None:
        self.inserted: list[tuple[str, list[dict]]] = []

    def insert(self, table: str, rows: list[dict]) -> list[dict]:
        self.inserted.append((table, rows))
        return rows


def test_settlement_carries_the_probs_its_clv_came_from() -> None:
    client = _FakePostgrest()
    written = write_settlements(
        client,
        [SettlementRow(pick_id=7, outcome="win", bet_prob=0.5, closing_prob=0.52, clv_pct=0.04)],
    )
    (table, rows) = client.inserted[0]
    assert (written, table) == (1, "pick_settlements")
    assert rows[0] == {
        "pick_id": 7,
        "outcome": "win",
        "bet_prob": 0.5,
        "closing_prob": 0.52,
        "clv_pct": 0.04,
    }


def test_clv_without_its_inputs_is_refused() -> None:
    with pytest.raises(ValueError, match="needs both the probs"):
        SettlementRow(pick_id=7, outcome="win", clv_pct=0.04)
    with pytest.raises(ValueError, match="needs both the probs"):
        SettlementRow(pick_id=7, outcome="win", bet_prob=0.5, clv_pct=0.04)


def test_a_settlement_with_no_clv_at_all_is_fine() -> None:
    """A postponed game or a missed closing sweep settles with an outcome and
    no CLV — that is a null row for Job F, not an error (fn_unsettled_picks
    returns closing_prob NULL in exactly that case)."""
    client = _FakePostgrest()
    write_settlements(client, [SettlementRow(pick_id=7, outcome="void", bet_prob=0.5)])
    assert client.inserted[0][1][0]["clv_pct"] is None


def test_unknown_outcome_is_refused() -> None:
    with pytest.raises(ValueError, match="outcome must be one of"):
        SettlementRow(pick_id=7, outcome="WIN")


def test_empty_batch_writes_nothing() -> None:
    client = _FakePostgrest()
    assert write_settlements(client, []) == 0
