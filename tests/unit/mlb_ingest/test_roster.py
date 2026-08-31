"""Offline tests via httpx.MockTransport — no real network."""

from __future__ import annotations

import httpx

from sbm.sports.mlb.ingest.statsapi.client import StatsApiClient
from sbm.sports.mlb.ingest.statsapi.roster import fetch_roster

ROSTER_PAYLOAD = {
    "roster": [
        {
            "person": {"id": 605400, "fullName": "Aaron Nola"},
            "position": {"abbreviation": "P"},
            "status": {"code": "A", "description": "Active"},
            "parentTeamId": 143,
        },
        {
            "person": {"id": 666969, "fullName": "Adolis García"},
            "position": {"abbreviation": "RF"},
            "status": {"code": "D60", "description": "Injured 60-Day"},
            "note": "Right latissimus dorsi tear",
            "parentTeamId": 143,
        },
        {
            # Missing person id entirely — must be skipped, not crash the pull.
            "position": {"abbreviation": "OF"},
            "status": {"code": "A"},
        },
    ]
}


def _client() -> StatsApiClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ROSTER_PAYLOAD)

    return StatsApiClient(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_roster_marks_active_player_not_injured() -> None:
    entries = fetch_roster(143, client=_client())
    nola = next(e for e in entries if e.player_id == 605400)
    assert nola.is_injured is False
    assert nola.position == "P"


def test_fetch_roster_marks_il_player_injured_with_note() -> None:
    entries = fetch_roster(143, client=_client())
    garcia = next(e for e in entries if e.player_id == 666969)
    assert garcia.is_injured is True
    assert garcia.status_code == "D60"
    assert garcia.note == "Right latissimus dorsi tear"


def test_fetch_roster_skips_entries_missing_player_id() -> None:
    entries = fetch_roster(143, client=_client())
    assert len(entries) == 2
