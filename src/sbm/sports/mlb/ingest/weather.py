"""Open-Meteo pre-game weather forecast — FORECAST ONLY, in both live and
backtest (model doc §3.7 RULE: "Backtests must use pre-game forecasts, not
observed actuals ... using realized weather is leakage that inflates
backtest CLV"). Every `WeatherForecast` this module returns carries
`is_forecast=True` unconditionally — there is no code path here that can
return an observed actual, which is what makes the flag structural rather
than just a label (backend doc §3.2's comment on `weather_snapshots.is_forecast`).

Two endpoints, same response shape, selected by which one answers a date
without leaking the future:
- `fetch_forecast` — the live forecast API, for real-time/near-term games.
- `fetch_historical_forecast` — Open-Meteo's **Historical Forecast API**
  (`historical-forecast-api.open-meteo.com`), for backtest. Confirmed live at
  build time: it serves the archived NWP model forecast as it stood at the
  time, not ERA5 reanalysis/observed-actuals — that's a *different* Open-Meteo
  product (`archive-api.open-meteo.com`), which this module never calls, on
  purpose (doc §10.6: "backtest weather via Open-Meteo historical forecast
  archive").

Coordinates come from `statsapi.venue.fetch_venue`, not hardcoded here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from sbm.sports.mlb.ingest.archive import (
    ENTITY_WEATHER,
    SOURCE_OPEN_METEO,
    CaptureSink,
    capture_payload,
)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

HOURLY_VARS = "temperature_2m,wind_speed_10m,wind_direction_10m,precipitation_probability"


@dataclass(frozen=True, slots=True)
class WeatherForecast:
    """One `weather_snapshots` row (backend doc §3.2), hourly-resolved."""

    valid_time_utc: datetime
    temp_f: float | None
    wind_mph: float | None
    wind_dir_deg: float | None
    precip_pct: float | None
    is_forecast: bool = True
    """Structurally always True from this module — see module docstring."""


def fetch_forecast(
    latitude: float,
    longitude: float,
    *,
    forecast_days: int = 3,
    client: httpx.Client | None = None,
    capture: CaptureSink | None = None,
) -> list[WeatherForecast]:
    """Pre-game forecast starting today (job A cadence + a pre-lock refresh,
    backend doc §2.4). Callers pick the hour matching the game's local start
    time; this returns the full hourly window.

    Pass `capture=` to archive the raw payload (backend doc §2.1). A forecast
    is only meaningful alongside when it was issued, and `WeatherForecast`
    carries the hour it is *valid for*, not the hour it was *pulled*."""
    return _fetch(
        FORECAST_URL,
        latitude,
        longitude,
        {"forecast_days": forecast_days},
        client,
        capture,
    )


def fetch_historical_forecast(
    latitude: float,
    longitude: float,
    target_date: date,
    *,
    client: httpx.Client | None = None,
    capture: CaptureSink | None = None,
) -> list[WeatherForecast]:
    """Archived NWP forecast for `target_date` — backtest-only, and still not
    the observed actual (model doc §3.7, §10.6)."""
    params = {"start_date": target_date.isoformat(), "end_date": target_date.isoformat()}
    return _fetch(HISTORICAL_FORECAST_URL, latitude, longitude, params, client, capture)


def _fetch(
    url: str,
    latitude: float,
    longitude: float,
    extra_params: dict,
    client: httpx.Client | None,
    capture: CaptureSink | None = None,
) -> list[WeatherForecast]:
    owns_client = client is None
    http = client or httpx.Client(timeout=10.0)
    try:
        resp = http.get(
            url,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "hourly": HOURLY_VARS,
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "UTC",  # avoid local-time ambiguity entirely
                **extra_params,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        capture_payload(
            capture,
            payload,
            source=SOURCE_OPEN_METEO,
            entity_type=ENTITY_WEATHER,
            entity_id=f"{latitude},{longitude}",
        )
        return _parse(payload)
    finally:
        if owns_client:
            http.close()


def _parse(payload: dict) -> list[WeatherForecast]:
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m")
    winds = hourly.get("wind_speed_10m")
    wind_dirs = hourly.get("wind_direction_10m")
    precip = hourly.get("precipitation_probability")
    return [
        WeatherForecast(
            valid_time_utc=datetime.fromisoformat(t).replace(tzinfo=UTC),
            temp_f=_at(temps, i),
            wind_mph=_at(winds, i),
            wind_dir_deg=_at(wind_dirs, i),
            precip_pct=_at(precip, i),
        )
        for i, t in enumerate(times)
    ]


def _at(values: list | None, i: int) -> float | None:
    if values is None or i >= len(values):
        return None
    return values[i]
