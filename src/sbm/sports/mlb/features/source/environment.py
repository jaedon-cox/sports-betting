"""Park and weather frames — the two families that are about the venue, not
the players.

Separated from the source proper because they share no inputs with it: neither
touches per-game form, injuries, or starters, and both are one flat frame
rather than a home/away pair.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from sbm.contracts.feature import AsOf
from sbm.sports.mlb.features.source import reads
from sbm.sports.mlb.features.source.context import GameContext
from sbm.sports.mlb.features.source.derive import PARK_COLUMNS, WEATHER_COLUMNS
from sbm.store.client import PostgrestClient


def park_frame(games: Mapping[str, GameContext], game_ids: list[str]) -> pd.DataFrame:
    """Structural venue facts, one row per game.

    `run_factor` is NaN for every row and that is not a gap to be filled
    quietly: no free numeric park factor exists. pybaseball's `park_codes()`
    returns Retrosheet ids and is broken upstream besides, so
    `features/park.py` documents this column as expected-null in v1. A guessed
    1.0 would read as "neutral park" rather than "unknown", which is a
    different and wrong claim.
    """
    rows = {
        gid: {
            "run_factor": np.nan,
            "roof_type": _venue(games, gid, "roof_type"),
            "turf_type": _venue(games, gid, "turf_type"),
            "orientation_deg": _venue(games, gid, "orientation_deg"),
        }
        for gid in game_ids
    }
    return _frame(rows, game_ids, PARK_COLUMNS)


def weather_frame(
    client: PostgrestClient,
    games: Mapping[str, GameContext],
    game_ids: list[str],
    as_of: AsOf,
) -> pd.DataFrame:
    """Newest forecast per game at `as_of`, joined to the park's orientation.

    `weather_snapshots` is keyed on the internal `games.id` while `game_ids`
    here are gamePks, so `GameContext.internal_id` is the bridge — the one
    place the surrogate reaches the feature layer, and only as a lookup key
    that never becomes a column.
    """
    contexts = [games[g] for g in game_ids if g in games]
    forecasts = reads.weather(
        client, game_ids=[c.internal_id for c in contexts], as_of=as_of.ts
    )
    by_game = forecasts.set_index("game_id") if not forecasts.empty else forecasts

    rows = {}
    for gid in game_ids:
        ctx = games.get(gid)
        found = None
        if ctx is not None and not by_game.empty and ctx.internal_id in by_game.index:
            found = by_game.loc[ctx.internal_id]
        rows[gid] = {
            "wind_mph": np.nan if found is None else found["wind_mph"],
            "wind_dir_deg": np.nan if found is None else found["wind_dir_deg"],
            "temp_f": np.nan if found is None else found["temp_f"],
            "precip_pct": np.nan if found is None else found["precip_pct"],
            "park_orientation_deg": _venue(games, gid, "orientation_deg"),
        }
    return _frame(rows, game_ids, WEATHER_COLUMNS)


def _venue(games: Mapping[str, GameContext], game_id: str, attribute: str):
    """A venue fact, or None when the game or its venue is unknown — a game
    off this slate, or one whose StatsAPI venue lookup returned nothing."""
    context = games.get(game_id)
    return getattr(context.venue, attribute, None) if context and context.venue else None


def _frame(rows: dict, game_ids: list[str], columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame.from_dict(rows, orient="index", columns=list(columns)).reindex(game_ids)
