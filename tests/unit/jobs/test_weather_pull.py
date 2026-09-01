"""Job A's per-venue forecast pull.

Every assertion here is about a documented *refusal* — no coordinates writes no
row, an observed reading is unreachable by construction, a 360-degree bearing is
wrapped rather than rejected by Postgres. `FakeStats` and `slate_with` come from
`test_reference_pulls.py`, which covers the other two Job A/B helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sbm.jobs.weather_pull import pull_weather
from sbm.sports.mlb.ingest.statsapi.venue import VenueInfo
from sbm.sports.mlb.ingest.weather import WeatherForecast
from tests.unit.jobs.fakes import FakeClient
from tests.unit.jobs.test_odds_sweep import game
from tests.unit.jobs.test_reference_pulls import FakeStats, slate_with

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def forecast(hour: int, wind_dir: float | None = 90.0) -> WeatherForecast:
    return WeatherForecast(
        valid_time_utc=datetime(2026, 7, 1, hour, tzinfo=UTC),
        temp_f=70.0 + hour,
        wind_mph=8.0,
        wind_dir_deg=wind_dir,
        precip_pct=10.0,
    )


def wire_weather(monkeypatch, *, venue: VenueInfo, hourly: list[WeatherForecast]) -> list[tuple]:
    seen: list[tuple] = []

    def fake_forecast(lat, lon, *, capture=None, **kwargs):
        seen.append((lat, lon))
        return hourly

    monkeypatch.setattr("sbm.jobs.weather_pull.fetch_venue", lambda vid, *, client: venue)
    monkeypatch.setattr("sbm.jobs.weather_pull.fetch_forecast", fake_forecast)
    return seen


PARK = VenueInfo(7, "Park", 40.8, -73.9, 30.0, "Open", "Grass")


def test_the_forecast_hour_nearest_first_pitch_is_the_one_written(monkeypatch) -> None:
    """Nearest, not floor: a 7:10pm start is better described by the 7pm reading
    than by whichever side of the boundary it lands on."""
    wire_weather(monkeypatch, venue=PARK, hourly=[forecast(22), forecast(23), forecast(0)])
    client = FakeClient()
    # `game()` starts at 23:05 UTC, so the 23:00 hour is nearest.
    pull_weather(client, stats=FakeStats(), slate=slate_with(game(555, "H", "A")), now=NOW)  # type: ignore[arg-type]
    assert client.rows_for("weather_snapshots")[0]["temp_f"] == 93.0


def test_one_forecast_call_per_venue_not_per_game(monkeypatch) -> None:
    """A doubleheader is two games at one ballpark and one hourly series."""
    seen = wire_weather(monkeypatch, venue=PARK, hourly=[forecast(23)])
    client = FakeClient()
    slate = slate_with(game(555, "H", "A"), game(556, "H", "A"))
    assert pull_weather(client, stats=FakeStats(), slate=slate, now=NOW) == 2  # type: ignore[arg-type]
    assert len(seen) == 1


def test_a_venue_without_coordinates_yields_no_row_rather_than_nulls(monkeypatch) -> None:
    """An empty forecast and a missing one are different facts; only one of them
    should look like data."""
    wire_weather(monkeypatch, venue=VenueInfo(7, "P", None, None, None, None, None), hourly=[])
    client = FakeClient()
    assert pull_weather(client, stats=FakeStats(), slate=slate_with(game(555, "H", "A")), now=NOW) == 0  # type: ignore[arg-type]
    assert client.rows_for("weather_snapshots") == []


def test_rows_are_always_forecasts_never_observed_actuals(monkeypatch) -> None:
    """Using realized weather is leakage that inflates backtest CLV (§3.7); this
    module has no code path that can produce one."""
    wire_weather(monkeypatch, venue=PARK, hourly=[forecast(23)])
    client = FakeClient()
    pull_weather(client, stats=FakeStats(), slate=slate_with(game(555, "H", "A")), now=NOW)  # type: ignore[arg-type]
    assert client.rows_for("weather_snapshots")[0]["is_forecast"] is True


def test_wind_direction_is_wrapped_into_the_smallint_check_range(monkeypatch) -> None:
    """Open-Meteo sends a float and 360 is legal there; `wind_dir_deg` is
    SMALLINT CHECK 0..359."""
    wire_weather(monkeypatch, venue=PARK, hourly=[forecast(23, wind_dir=360.0)])
    client = FakeClient()
    pull_weather(client, stats=FakeStats(), slate=slate_with(game(555, "H", "A")), now=NOW)  # type: ignore[arg-type]
    assert client.rows_for("weather_snapshots")[0]["wind_dir_deg"] == 0


def test_a_null_wind_direction_stays_null(monkeypatch) -> None:
    wire_weather(monkeypatch, venue=PARK, hourly=[forecast(23, wind_dir=None)])
    client = FakeClient()
    pull_weather(client, stats=FakeStats(), slate=slate_with(game(555, "H", "A")), now=NOW)  # type: ignore[arg-type]
    assert client.rows_for("weather_snapshots")[0]["wind_dir_deg"] is None
