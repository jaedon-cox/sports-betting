"""The five RPC calls behind `PostgrestSnapshotSource`, as DataFrames.

One function per Postgres function (db/migrations/018), doing nothing but
calling it and shaping the result. All filtering — the as-of cut especially —
happens in SQL rather than here, so a caller cannot forget it: the functions
themselves enforce `game_date < as_of` (CLAUDE.md rule 4).

`game_date` comes back as an ISO string over PostgREST and is parsed to
datetime here, because `recency.recency_weighted_by_entity` compares it against
`as_of` and a string comparison would silently succeed while ordering wrong.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from sbm.store.client import PostgrestClient

_NUMERIC_PITCHER = (
    "pitches", "csw", "batters_faced", "outs", "strikeouts", "walks",
    "hit_by_pitch", "home_runs", "ground_balls", "fly_balls", "line_drives",
    "popups", "siera",
)
_NUMERIC_BULLPEN = (
    "appearances", "pitches", "outs", "batters_faced", "strikeouts", "walks",
    "hit_by_pitch", "home_runs", "ground_balls", "fly_balls", "line_drives", "popups",
)


_TEXT_KEYS = ("player_id", "pitching_team", "batting_team", "opp_hand", "throws")
"""Columns used as lookup keys, coerced to `str` unconditionally.

This is not defensive tidying — it is the guard against the single nastiest
failure this module can have. `player_id` is TEXT in Postgres, but anything
that hands back a numeric (a fixture, a driver change, a future view that
casts) makes every `rates.loc[pid]` lookup miss silently, because a str key
against an int64 index is simply absent rather than an error. The result is a
feature frame of NaN, which `columns._or_default` then fills with league
averages — so the model prices the whole slate as thirty average teams and
publishes picks that look entirely plausible.

Observed exactly once, in a harness whose rows came back as int64. There is no
downstream assertion that would catch it, so the types are pinned here.
"""


def _frame(rows: Any, *, numeric: tuple[str, ...], columns: tuple[str, ...]) -> pd.DataFrame:
    """Rows -> a typed frame, with `game_date` parsed and types pinned.

    An empty result returns an empty frame carrying the full column set rather
    than a bare `DataFrame()`: every consumer indexes columns by name, and a
    slate with no history at all should flow through as NaN features rather
    than raise a KeyError three layers down.
    """
    frame = pd.DataFrame(list(rows or []))
    if frame.empty:
        return pd.DataFrame(columns=list(columns))
    if "game_date" in frame.columns:
        frame["game_date"] = pd.to_datetime(frame["game_date"])
    for column in numeric:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in _TEXT_KEYS:
        if column in frame.columns:
            frame[column] = frame[column].astype("object").map(
                lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
            )
    return frame


def pitcher_game_form(
    client: PostgrestClient, *, player_ids: list[str], since: date, as_of: date
) -> pd.DataFrame:
    """Per-game rows for the named pitchers, strictly before `as_of`."""
    if not player_ids:
        return _frame([], numeric=_NUMERIC_PITCHER, columns=("player_id", "game_date"))
    rows = client.rpc(
        "fn_pitcher_game_form",
        {
            "p_player_ids": player_ids,
            "p_from": since.isoformat(),
            "p_as_of": as_of.isoformat(),
        },
    )
    return _frame(
        rows,
        numeric=_NUMERIC_PITCHER,
        columns=("player_id", "game_date", "throws", "is_start", *_NUMERIC_PITCHER),
    )


def bullpen_game_form(
    client: PostgrestClient, *, teams: list[str], since: date, as_of: date
) -> pd.DataFrame:
    """Per (club, date) relief totals, strictly before `as_of`."""
    if not teams:
        return _frame([], numeric=_NUMERIC_BULLPEN, columns=("pitching_team", "game_date"))
    rows = client.rpc(
        "fn_bullpen_game_form",
        {"p_teams": teams, "p_from": since.isoformat(), "p_as_of": as_of.isoformat()},
    )
    return _frame(
        rows,
        numeric=_NUMERIC_BULLPEN,
        columns=("pitching_team", "game_date", *_NUMERIC_BULLPEN),
    )


def team_batting_form(
    client: PostgrestClient, *, teams: list[str], since: date, as_of: date
) -> pd.DataFrame:
    """Per (club, date, opposing hand) batting rows, strictly before `as_of`."""
    if not teams:
        return _frame([], numeric=(), columns=("batting_team", "game_date", "opp_hand"))
    rows = client.rpc(
        "fn_team_batting_form",
        {"p_teams": teams, "p_from": since.isoformat(), "p_as_of": as_of.isoformat()},
    )
    return _frame(
        rows,
        numeric=("plate_appearances", "xwoba_sum"),
        columns=("batting_team", "game_date", "opp_hand", "plate_appearances", "xwoba_sum"),
    )


def injury_status(
    client: PostgrestClient, *, team_ids: list[int], since: datetime, as_of: datetime
) -> pd.DataFrame:
    """Newest non-active status per player for the given clubs.

    `since` bounds the lookback because absence is what marks a player
    available: `roster_pull.py` writes no row for an active player, so a stale
    row older than the club's last sweep describes someone since reinstated
    (db/migrations/018's header spells this out).
    """
    if not team_ids:
        return _frame([], numeric=(), columns=("player_id", "team_id", "status"))
    rows = client.rpc(
        "fn_injury_status_asof",
        {
            "p_team_ids": team_ids,
            "p_since": since.isoformat(),
            "p_as_of": as_of.isoformat(),
        },
    )
    return _frame(rows, numeric=("team_id",), columns=("player_id", "team_id", "status"))


def weather(
    client: PostgrestClient, *, game_ids: list[int], as_of: datetime
) -> pd.DataFrame:
    """Newest forecast per game at `as_of`, keyed by the internal `games.id`."""
    columns = ("game_id", "temp_f", "wind_mph", "wind_dir_deg", "precip_pct")
    if not game_ids:
        return _frame([], numeric=(), columns=columns)
    rows = client.rpc(
        "fn_weather_asof", {"p_game_ids": game_ids, "p_as_of": as_of.isoformat()}
    )
    return _frame(rows, numeric=columns[1:], columns=columns)
