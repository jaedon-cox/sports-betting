"""The `raw_snapshots` drain — backend doc §2.1's append-only-blob requirement."""

from __future__ import annotations

from datetime import UTC, datetime

from sbm.jobs.archive import archive_odds_payload, drain
from sbm.sports.mlb.ingest.archive import CaptureList, RawCapture
from tests.unit.jobs.fakes import FakeClient

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def test_capture_fields_map_onto_the_row_with_no_translation_layer() -> None:
    """`RawCapture` and `RawSnapshotRow` are 1:1 on purpose, so `ingest` never
    has to import `store`."""
    capture = CaptureList()
    capture(
        RawCapture(
            sport="mlb", source="mlb_statsapi", entity_type="schedule",
            entity_id="2026-07-01", payload={"dates": []}, pulled_at_utc=NOW,
        )
    )
    client = FakeClient()
    assert drain(client, capture) == 1  # type: ignore[arg-type]
    table, rows = client.inserts[0]
    assert table == "raw_snapshots"
    assert rows[0]["entity_id"] == "2026-07-01"
    assert rows[0]["pulled_at_utc"] == NOW.isoformat()


def test_an_empty_capture_issues_no_request() -> None:
    client = FakeClient()
    assert drain(client, CaptureList()) == 0  # type: ignore[arg-type]
    assert client.inserts == []


def test_the_odds_array_is_wrapped_rather_than_coerced() -> None:
    """`raw_snapshots.payload` is JSONB-object shaped and `RawSnapshotRow.payload`
    is typed `dict`; The Odds API sends an array."""
    client = FakeClient()
    archive_odds_payload(
        client, [{"id": "a"}, {"id": "b"}], entity_id="open", pulled_at_utc=NOW  # type: ignore[arg-type]
    )
    row = client.rows_for("raw_snapshots")[0]
    assert row["payload"] == {"games": [{"id": "a"}, {"id": "b"}]}
    assert row["entity_type"] == "odds"
