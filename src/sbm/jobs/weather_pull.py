"""Pre-game weather forecast per game -> `weather_snapshots` (Job A, §2.1/§2.4).

Forecast only, never an observed actual — `ingest/weather.py` has no code path
that can return one, so `is_forecast` is structural rather than a label (model
doc §3.7: using realized weather is leakage that inflates backtest CLV).

One forecast call per *venue*, not per game: a doubleheader is two games at one
ballpark, and Open-Meteo's response is an hourly series covering both. Venue
coordinates come from `statsapi.venue.fetch_venue`, not a hardcoded table.

The raw payload is archived through `capture=` (§2.1). A forecast is only
meaningful alongside when it was issued, and `WeatherForecast` carries the hour
it is *valid for*, not the hour it was pulled.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from sbm.jobs.slate_ingest import Slate
from sbm.sports.mlb.ingest.archive import CaptureList
from sbm.sports.mlb.ingest.statsapi import StatsApiClient, fetch_venue
from sbm.sports.mlb.ingest.weather import WeatherForecast, fetch_forecast
from sbm.store.client import PostgrestClient
from sbm.store.snapshots import WeatherSnapshotRow, insert_weather_snapshots


def pull_weather(
    client: PostgrestClient,
    *,
    stats: StatsApiClient,
    slate: Slate,
    now: datetime,
    capture: CaptureList | None = None,
) -> int:
    """Write one forecast row per game with a start time and a locatable venue.

    Returns the row count. A game whose venue has no coordinates yields nothing
    rather than a row of nulls — an empty forecast and a missing one are
    different facts, and only one of them should look like data.
    """
    forecasts: dict[int, list[WeatherForecast]] = {}
    rows: list[WeatherSnapshotRow] = []
    for game in slate.games:
        game_id = slate.game_ids.get(str(game.game_pk))
        if game_id is None or game.venue_id is None or game.start_time_utc is None:
            continue
        if game.venue_id not in forecasts:
            forecasts[game.venue_id] = _venue_forecast(stats, game.venue_id, capture)
        hourly = _nearest_hour(forecasts[game.venue_id], game.start_time_utc)
        if hourly is None:
            continue
        rows.append(
            WeatherSnapshotRow(
                game_id=game_id,
                is_forecast=True,
                captured_at_utc=now,
                temp_f=hourly.temp_f,
                wind_mph=hourly.wind_mph,
                wind_dir_deg=_bearing(hourly.wind_dir_deg),
                precip_pct=hourly.precip_pct,
            )
        )
    insert_weather_snapshots(client, rows)
    return len(rows)


def _venue_forecast(
    stats: StatsApiClient, venue_id: int, capture: CaptureList | None
) -> list[WeatherForecast]:
    """One venue's hourly series, or `[]` if the forecast could not be had.

    **A weather failure must not fail Job A.** The job's load-bearing output is
    the opening odds snapshot — 3 of 500 monthly credits, and the price every
    `bet_prob` and therefore every CLV number is measured against (§2.5). It is
    bought *after* this runs, so an exception here costs the day's anchor price
    to save a feature the model already defaults through: `columns._or_default`
    substitutes the league-average run environment for a missing forecast, per
    doc §5.4's "assume average beats crashing the pipeline".

    Open-Meteo is free, unauthenticated and rate-limited per IP, and GitHub
    Actions runners come from shared Azure ranges — so a throttle is a routine
    operating condition, not an anomaly. Observed in production as an empty
    200 body (a `JSONDecodeError`, not a 4xx), which is why `ValueError` is
    caught alongside `httpx.HTTPError` rather than trusting `raise_for_status`.

    Failures are printed, never swallowed: the run stays green because the job
    did its real work, and the operator still sees which venue degraded and
    why. `pull_weather`'s row count dropping below the slate size is the other
    signal.
    """
    try:
        venue = fetch_venue(venue_id, client=stats)
        if venue.latitude is None or venue.longitude is None:
            return []
        return fetch_forecast(venue.latitude, venue.longitude, capture=capture)
    except (httpx.HTTPError, ValueError) as exc:
        print(f"weather: venue {venue_id} degraded to no forecast — {type(exc).__name__}: {exc}")
        return []


def _nearest_hour(hourly: list[WeatherForecast], start_time_utc: datetime) -> WeatherForecast | None:
    """The forecast hour closest to first pitch.

    Nearest rather than floor: a 7:10pm start is better described by the 7pm
    reading than by whichever side of the hour boundary it happens to fall on.
    """
    if not hourly:
        return None
    return min(hourly, key=lambda f: abs((f.valid_time_utc - start_time_utc).total_seconds()))


def _bearing(degrees: float | None) -> int | None:
    """`weather_snapshots.wind_dir_deg` is SMALLINT CHECK 0..359; Open-Meteo
    sends a float and 360 is a legal value there but not here."""
    return None if degrees is None else int(round(degrees)) % 360
