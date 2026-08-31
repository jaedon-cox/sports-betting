"""Offline tests via httpx.MockTransport — no real network."""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx

from sbm.sports.mlb.ingest.weather import (
    FORECAST_URL,
    HISTORICAL_FORECAST_URL,
    fetch_forecast,
    fetch_historical_forecast,
)

PAYLOAD = {
    "hourly": {
        "time": ["2026-08-29T00:00", "2026-08-29T01:00"],
        "temperature_2m": [80.3, 76.6],
        "wind_speed_10m": [3.3, 5.4],
        "wind_direction_10m": [318, 321],
        "precipitation_probability": [7, 2],
    }
}


def _client(seen_urls: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=PAYLOAD)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_forecast_hits_the_live_endpoint_and_is_always_forecast() -> None:
    seen: list[str] = []
    rows = fetch_forecast(40.8, -73.9, client=_client(seen))
    assert all(row.is_forecast is True for row in rows)
    assert rows[0].valid_time_utc == datetime(2026, 8, 29, 0, 0, tzinfo=UTC)
    assert rows[0].temp_f == 80.3
    assert seen[0].startswith(FORECAST_URL)


def test_fetch_historical_forecast_hits_the_historical_endpoint_never_the_actuals_one() -> None:
    seen: list[str] = []
    rows = fetch_historical_forecast(40.8, -73.9, date(2024, 6, 1), client=_client(seen))
    assert all(row.is_forecast is True for row in rows)
    assert seen[0].startswith(HISTORICAL_FORECAST_URL)
    assert "archive-api.open-meteo.com" not in seen[0]


def test_parse_handles_missing_hourly_series_defensively() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hourly": {"time": ["2026-08-29T00:00"]}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    rows = fetch_forecast(40.8, -73.9, client=client)
    assert rows[0].temp_f is None
    assert rows[0].wind_mph is None
