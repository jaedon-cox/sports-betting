"""Offline tests via httpx.MockTransport — no real network."""

from __future__ import annotations

import httpx

from sbm.sports.mlb.ingest.statsapi.client import StatsApiClient
from sbm.sports.mlb.ingest.statsapi.venue import fetch_venue

VENUE_PAYLOAD = {
    "venues": [
        {
            "id": 2681,
            "name": "Citizens Bank Park",
            "location": {
                "defaultCoordinates": {"latitude": 39.90539086, "longitude": -75.16716957},
                "azimuthAngle": 9.0,
            },
            "fieldInfo": {"turfType": "Grass", "roofType": "Open"},
        }
    ]
}


def _client(payload: dict) -> StatsApiClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return StatsApiClient(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_venue_parses_coordinates_orientation_roof_turf() -> None:
    venue = fetch_venue(2681, client=_client(VENUE_PAYLOAD))
    assert venue.latitude == 39.90539086
    assert venue.longitude == -75.16716957
    assert venue.orientation_deg == 9.0
    assert venue.roof_type == "Open"
    assert venue.turf_type == "Grass"
    assert venue.name == "Citizens Bank Park"


def test_fetch_venue_handles_empty_response_defensively() -> None:
    venue = fetch_venue(9999, client=_client({"venues": []}))
    assert venue.venue_id == 9999
    assert venue.latitude is None
