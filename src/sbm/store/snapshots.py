"""Append-only snapshot writers `ingest` needs — one row shape and one
insert function per point-in-time snapshot table (db/migrations/004 and
005). Every function here is a plain client.insert(); the only "logic"
is shaping the row and stringifying timestamps for JSON.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sbm.store.client import PostgrestClient


@dataclass(frozen=True, slots=True)
class LineSnapshotRow:
    game_id: int
    sport: str
    market: str
    side: str
    price_american: int
    captured_at_utc: datetime
    line: float | None = None
    """Spread/total number this price is quoted at; NULL for moneyline."""
    implied_prob_devigged: float | None = None
    devig_method: str | None = None
    source: str = "pinnacle"
    is_closing: bool = False

    def __post_init__(self) -> None:
        """Mirror 004's CHECK ((implied_prob_devigged IS NULL) = (devig_method
        IS NULL)) locally, so the pairing fails here rather than as a Postgres
        constraint violation on the first real pipeline write. `picks` records
        the per-row de-vig method for the same reason (003): the table is
        append-only, so a backtest has to be able to prove which method
        produced a given number even after the configured default changes.
        """
        if (self.implied_prob_devigged is None) != (self.devig_method is None):
            raise ValueError(
                "implied_prob_devigged and devig_method must both be set or "
                f"both be None (got {self.implied_prob_devigged!r}, {self.devig_method!r})"
            )


@dataclass(frozen=True, slots=True)
class LineupSnapshotRow:
    game_id: int
    team_id: int
    batting_order: list[str]
    captured_at_utc: datetime
    is_confirmed: bool = False


@dataclass(frozen=True, slots=True)
class InjurySnapshotRow:
    player_id: str
    team_id: int
    status: str
    captured_at_utc: datetime
    note: str | None = None


@dataclass(frozen=True, slots=True)
class WeatherSnapshotRow:
    game_id: int
    is_forecast: bool
    captured_at_utc: datetime
    temp_f: float | None = None
    wind_mph: float | None = None
    wind_dir_deg: int | None = None
    precip_pct: float | None = None


@dataclass(frozen=True, slots=True)
class RawSnapshotRow:
    sport: str
    source: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    pulled_at_utc: datetime


def _row(dc: Any) -> dict[str, Any]:
    """dataclass -> JSON-safe dict: stringify any datetime field."""
    d = asdict(dc)
    for key, value in d.items():
        if isinstance(value, datetime):
            d[key] = value.isoformat()
    return d


def insert_line_snapshots(client: PostgrestClient, rows: list[LineSnapshotRow]) -> list[dict[str, Any]]:
    return client.insert("line_snapshots", [_row(r) for r in rows])


def insert_lineup_snapshots(client: PostgrestClient, rows: list[LineupSnapshotRow]) -> list[dict[str, Any]]:
    return client.insert("lineup_snapshots", [_row(r) for r in rows])


def insert_injury_snapshots(client: PostgrestClient, rows: list[InjurySnapshotRow]) -> list[dict[str, Any]]:
    return client.insert("injury_snapshots", [_row(r) for r in rows])


def insert_weather_snapshots(client: PostgrestClient, rows: list[WeatherSnapshotRow]) -> list[dict[str, Any]]:
    return client.insert("weather_snapshots", [_row(r) for r in rows])


def insert_raw_snapshots(client: PostgrestClient, rows: list[RawSnapshotRow]) -> list[dict[str, Any]]:
    return client.insert("raw_snapshots", [_row(r) for r in rows])
