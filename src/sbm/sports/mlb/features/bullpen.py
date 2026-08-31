"""Bullpen fatigue + skill (model doc §3.2, §10.2/§10.3).

Fatigue is the doc's flagged **primary alpha source**: "computationally
expensive, updates intraday, and the market is demonstrably slow on it."
`fatigue` here is expected to already be a recency-weighted (EWMA, 5-7 game
half-life per §10.1) trailing pitch-count load per team — real per-appearance
granularity exists via `ingest/savant.py`'s pitch-level pulls joined to
roster team assignment, so unlike starter SIERA this one has genuine
per-appearance data to EWMA over. `builder.py` does that weighting once; this
module only assembles the per-game columns.

`xfip` is bullpen-level skill (10-14 game half-life, §10.1) — season-level
FanGraphs relief aggregate, same "value as of the pull" caveat as
`pitcher.py`'s SIERA.
"""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = ("fatigue", "xfip", "unavailable_arms")
"""Columns `home`/`away` must carry, one row per game_id.

`unavailable_arms`: count of relief arms flagged unavailable (back-to-back
appearances, IL) as of `as_of` — feeds `bullpen_exposure_risk` alongside TTO
(`features/tto.py`)."""


def compute_bullpen_features(home: pd.DataFrame, away: pd.DataFrame) -> pd.DataFrame:
    """`home`/`away` are indexed by game_id with `REQUIRED_COLUMNS`."""
    return _side_columns(home, "home").join(_side_columns(away, "away"), how="outer")


def _side_columns(side: pd.DataFrame, prefix: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            f"{prefix}_bullpen_fatigue": side["fatigue"],
            f"{prefix}_bullpen_xfip": side["xfip"],
            f"{prefix}_bullpen_unavailable_arms": side["unavailable_arms"],
        },
        index=side.index,
    )
