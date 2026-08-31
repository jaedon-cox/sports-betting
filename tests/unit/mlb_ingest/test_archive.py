"""The `raw_snapshots` capture seam (backend doc §2.1) — offline, no network.

What these pin down is the property that makes §2.1 satisfiable at all: the
fetcher hands over the payload it *received*, not the typed rows it parsed.
Every fetcher below deliberately drops fields during parsing, so a capture
that matched the parsed output would be evidence of the bug, not the fix.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime

import httpx

from sbm.sports.mlb.ingest.archive import (
    ENTITY_ROSTER,
    ENTITY_SCHEDULE,
    ENTITY_WEATHER,
    SOURCE_OPEN_METEO,
    SOURCE_STATSAPI,
    SPORT,
    CaptureList,
    RawCapture,
    capture_payload,
)
from sbm.sports.mlb.ingest.statsapi.client import StatsApiClient
from sbm.sports.mlb.ingest.statsapi.roster import fetch_roster
from sbm.sports.mlb.ingest.statsapi.schedule import fetch_schedule
from sbm.sports.mlb.ingest.throttle import Throttle
from sbm.sports.mlb.ingest.weather import fetch_forecast

SCHEDULE_PAYLOAD = {
    "dates": [
        {
            "games": [
                {
                    "gamePk": 823452,
                    "gameDate": "2026-06-15T22:40:00Z",
                    "officialDate": "2026-06-15",
                    "status": {"abstractGameState": "Preview", "detailedState": "Scheduled"},
                    "venue": {"id": 2681, "name": "Citizens Bank Park"},
                    "teams": {
                        "away": {"team": {"id": 146, "name": "Miami Marlins"}},
                        "home": {"team": {"id": 143, "name": "Philadelphia Phillies"}},
                    },
                    # Not represented on ScheduledGame — the reason full-fidelity
                    # archival is a separate concern from parsing.
                    "seriesDescription": "Regular Season",
                }
            ]
        }
    ]
}

ROSTER_PAYLOAD = {
    "roster": [
        {
            "person": {"id": 605400, "fullName": "Aaron Nola"},
            "position": {"abbreviation": "P"},
            "status": {"code": "D15", "description": "15-Day Injured List"},
            "note": "right ankle sprain",
            "parentTeamId": 143,
        }
    ]
}

WEATHER_PAYLOAD = {
    "hourly": {
        "time": ["2026-08-29T00:00"],
        "temperature_2m": [80.3],
        "wind_speed_10m": [3.3],
        "wind_direction_10m": [318],
        "precipitation_probability": [7],
    },
    "elevation": 8.0,  # dropped by _parse — must still survive into the archive
}


def _statsapi(payload: dict) -> StatsApiClient:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    return StatsApiClient(
        client=httpx.Client(transport=transport), throttle=Throttle(min_interval_s=0.0)
    )


def _httpx(payload: dict) -> httpx.Client:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    return httpx.Client(transport=transport)


def test_no_capture_sink_means_no_behaviour_change() -> None:
    """The seam must be free when unused — jobs opt in, fetchers don't require it."""
    games = fetch_schedule(date(2026, 6, 15), client=_statsapi(SCHEDULE_PAYLOAD))
    assert games[0].game_pk == 823452


def test_schedule_archives_the_untouched_payload() -> None:
    sink = CaptureList()
    fetch_schedule(date(2026, 6, 15), client=_statsapi(SCHEDULE_PAYLOAD), capture=sink)

    (capture,) = sink.captures
    assert capture.payload == SCHEDULE_PAYLOAD
    # The field ScheduledGame has no home for still made it to the archive.
    assert capture.payload["dates"][0]["games"][0]["seriesDescription"] == "Regular Season"
    assert capture.source == SOURCE_STATSAPI
    assert capture.entity_type == ENTITY_SCHEDULE
    assert capture.entity_id == "2026-06-15"
    assert capture.sport == SPORT


def test_roster_archives_the_untouched_payload_keyed_by_team() -> None:
    sink = CaptureList()
    fetch_roster(143, client=_statsapi(ROSTER_PAYLOAD), capture=sink)

    (capture,) = sink.captures
    assert capture.payload == ROSTER_PAYLOAD
    assert capture.entity_type == ENTITY_ROSTER
    assert capture.entity_id == "143"


def test_weather_archives_fields_the_parse_discards() -> None:
    sink = CaptureList()
    rows = fetch_forecast(40.8, -73.9, client=_httpx(WEATHER_PAYLOAD), capture=sink)

    (capture,) = sink.captures
    assert capture.payload["elevation"] == 8.0
    assert not hasattr(rows[0], "elevation")
    assert capture.source == SOURCE_OPEN_METEO
    assert capture.entity_type == ENTITY_WEATHER
    assert capture.entity_id == "40.8,-73.9"


def test_pulled_at_is_timezone_aware_utc() -> None:
    """`pulled_at_utc` is the only public-availability lower bound we have
    (model doc §5.1) — a naive timestamp would make as-of joins ambiguous."""
    before = datetime.now(UTC)
    sink = CaptureList()
    fetch_roster(143, client=_statsapi(ROSTER_PAYLOAD), capture=sink)

    pulled = sink.captures[0].pulled_at_utc
    assert pulled.tzinfo is not None
    assert pulled.utcoffset() == UTC.utcoffset(None)
    assert before <= pulled <= datetime.now(UTC)


def test_capture_fields_match_db_raw_snapshot_row_exactly() -> None:
    """`archive.py` promises a job can do `RawSnapshotRow(**asdict(capture))`
    without a translation layer — this fails the moment either side drifts."""
    from sbm.store.snapshots import RawSnapshotRow

    capture = RawCapture(
        sport=SPORT,
        source=SOURCE_STATSAPI,
        entity_type=ENTITY_ROSTER,
        entity_id="143",
        payload={"roster": []},
        pulled_at_utc=datetime.now(UTC),
    )
    row = RawSnapshotRow(**asdict(capture))
    assert row.entity_id == "143"


def test_capture_payload_is_a_noop_without_a_sink() -> None:
    capture_payload(None, {"a": 1}, source="x", entity_type="y", entity_id="z")
