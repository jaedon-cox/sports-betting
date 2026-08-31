"""Times-Through-Order penalty (model doc §3.3, §10.2/§10.3): a starter's
expected innings pitched determines how much bullpen exposure a game carries
— "interacts with bullpen exposure; matters for totals and run-line. Must
use *projected* (point-in-time) usage, not realized."

`expected_ip` is expected to already be a recency-weighted (EWMA, same
20-30 game half-life bucket as starter quality, §10.1) trailing
innings-per-start figure — computed once in `builder.py`, not here.
`scheduled_innings` is the game's regulation length (9, or a shortened
doubleheader game) from `ingest/statsapi/schedule.py`.
"""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = ("expected_ip", "scheduled_innings")
"""Columns `home`/`away` must carry, one row per game_id."""


def compute_tto_features(home: pd.DataFrame, away: pd.DataFrame) -> pd.DataFrame:
    """`home`/`away` are indexed by game_id with `REQUIRED_COLUMNS`."""
    return _side_columns(home, "home").join(_side_columns(away, "away"), how="outer")


def _side_columns(side: pd.DataFrame, prefix: str) -> pd.DataFrame:
    bullpen_exposure_ip = (side["scheduled_innings"] - side["expected_ip"]).clip(lower=0.0)
    return pd.DataFrame(
        {
            f"{prefix}_starter_expected_ip": side["expected_ip"],
            f"{prefix}_bullpen_exposure_ip": bullpen_exposure_ip,
        },
        index=side.index,
    )
