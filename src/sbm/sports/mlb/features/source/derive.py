"""Window constants and the two derivations that are volumes, not rates.

Kept out of `rates.py` because nothing here is EWMA-weighted, and that is the
distinction worth having a file boundary on: `rates.py` produces recency-
weighted season rates, this produces short-window totals where weighting would
destroy the signal.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from typing import Callable, Mapping

from sbm.contracts.feature import AsOf
from sbm.sports.mlb.features.source.context import GameContext
from sbm.sports.mlb.features.source.rates import utc_aligned

FORM_WINDOW_DAYS = 210
"""How far back the form window reaches — a full season plus spring. An EWMA
with a 12-game half-life draws no measurable weight from beyond it, and the
bound keeps the read off a full-history scan."""

INJURY_LOOKBACK_HOURS = 36
"""How stale an IL row may be before the player is treated as reinstated.

`roster_pull.py` writes rows only for non-active players, so a return to active
writes nothing and a player's last IL row would otherwise describe him forever.
Job B sweeps hourly, so a row older than ~a day and a half means the sweeps
have stopped seeing him — he is back. Deliberately wider than the cadence: a
few missed sweeps should not mass-reinstate a roster."""

FATIGUE_WINDOW_DAYS = 3
"""Backend doc §2.1 calls bullpen fatigue a back-to-back-appearances signal.
Three days covers a series, which is the horizon a manager actually manages a
pen over."""

NORMAL_RELIEF_PITCHES_PER_DAY = 57.0
RELIEF_PITCHES_SCALE = 19.0
"""Median and standard deviation of a club's relief pitches per day over a
rolling three-day window. MEASURED, not assumed: 2,328 club-days of 2026
Statcast give median 57.0, sd 19.0, 5th-95th percentile 28 to 90.

These exist because `bullpen_fatigue` has to come out **dimensionless and
centred on zero**, and nothing in either layer said so. `model/mean.py` adds
`coef_opp_bullpen_fatigue * fatigue` in LOG space, and `model/columns.py`
defaults a missing value to `0.0` — so zero means "league-normal workload" and
the coefficient expects roughly unit scale. Handing it raw pitches per day
(~57) produced `exp(0.05 * 57)` and a projected 46 runs per team.

Neither layer documented the contract, so this is the first place it is
written down. If `coef_opp_bullpen_fatigue` is ever calibrated against settled
history, it must be calibrated against THIS scale."""

PITCHER_COLUMNS = (
    "siera", "xfip", "csw_pct", "gb_pct", "hand", "innings_pitched", "starter_injured",
)
BULLPEN_COLUMNS = ("fatigue", "xfip", "unavailable_arms")
OFFENSE_COLUMNS = ("wrc_plus", "xwoba_vs_opp_hand", "key_injuries_count")
TTO_COLUMNS = ("expected_ip", "scheduled_innings")
PARK_COLUMNS = ("run_factor", "roof_type", "turf_type", "orientation_deg")
WEATHER_COLUMNS = ("wind_mph", "wind_dir_deg", "temp_f", "precip_pct", "park_orientation_deg")


def bullpen_fatigue(history: pd.DataFrame, as_of: AsOf) -> pd.Series:
    """Relief pitches thrown by a club in the trailing window, per day.

    Returned as a standardised index, not a pitch count: 0.0 is a league-normal
    workload, +1.0 is one standard deviation of extra work. That is the scale
    `model/mean.py` multiplies its log-space coefficient by — see the constants
    above for why this is stated here rather than inferred.

    Deliberately NOT recency-weighted. Fatigue is a short-window volume — did
    this pen work last night — and an EWMA with a season-scale half-life would
    wash out exactly the signal being measured. Same reasoning that keeps
    `innings_pitched` unweighted in `rates.py`, on a much shorter horizon.

    A club with no games in the window gets no row, which reaches
    `columns._or_default`'s 0.0 — correctly, since a pen that has not pitched
    in three days is rested, which is what league-normal-or-better means here.
    """
    if history.empty:
        return pd.Series(dtype=float)
    history, ts = utc_aligned(history, as_of.ts)
    recent = history[history["game_date"] > (ts - timedelta(days=FATIGUE_WINDOW_DAYS))]
    if recent.empty:
        return pd.Series(dtype=float)
    per_day = recent.groupby("pitching_team")["pitches"].sum() / float(FATIGUE_WINDOW_DAYS)
    return (per_day - NORMAL_RELIEF_PITCHES_PER_DAY) / RELIEF_PITCHES_SCALE


def expected_ip(history: pd.DataFrame) -> dict[str, float]:
    """Mean innings per start — `features/tto.py`'s starter-workload input.

    A plain mean rather than an EWMA: the TTO term asks how deep this starter
    typically goes, which is a stable role fact (opener, bulk, workhorse) far
    more than it is recent form.
    """
    if history.empty:
        return {}
    starts = history[history["is_start"].astype(bool)]
    if starts.empty:
        return {}
    return (starts.groupby("player_id")["outs"].mean() / 3.0).to_dict()


def sided_frames(
    games: Mapping[str, GameContext],
    game_ids: list[str],
    columns: tuple[str, ...],
    row: Callable[[GameContext, str], dict],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`row(ctx, side)` for both sides, as two frames aligned on `game_ids`.

    Every side-split family has the same shape — one row per game, identical
    columns on each side — so only the row builder differs between them. A
    game_id with no context yields an all-NaN row rather than raising: it is
    off this slate, and `build()` reindexes to `game_ids` regardless.
    """
    out = []
    for side in ("home", "away"):
        built = {gid: (row(games[gid], side) if gid in games else {}) for gid in game_ids}
        out.append(
            pd.DataFrame.from_dict(built, orient="index", columns=list(columns)).reindex(game_ids)
        )
    return out[0], out[1]
