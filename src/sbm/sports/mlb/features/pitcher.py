"""Starting-pitcher quality (model doc §10.2/§10.3): SIERA with an xFIP
fallback for small samples, CSW%, GB%, handedness.

Recency-weighting (doc §10.1: starters, 20-30 game half-life) happens once,
in `builder.py`, via `core`'s EWMA — this module does no recency math itself,
it only assembles per-game columns from already point-in-time, already
EWMA'd per-pitcher values.

**Known limitation (flagged to `model`):** FanGraphs' `pitching_stats` (via
`ingest/pybaseball.py`) is a season-to-date aggregate, not a per-start time
series, so there is no verified per-start SIERA decomposition to EWMA over —
`home`/`away` below are expected to already be "value as of the most recent
point-in-time pull," not a true trailing-starts EWMA. CSW%/GB% *do* have
genuine per-start granularity (from `ingest/savant.py`'s pitch-level data),
so those two are true EWMAs once `builder.py` wires them.
"""

from __future__ import annotations

import pandas as pd

SMALL_SAMPLE_INNINGS = 30.0
"""Below this many innings pitched this season, prefer xFIP over SIERA —
SIERA is noisier at small samples (model doc §3.1: "xFIP for small-N")."""

REQUIRED_COLUMNS = ("siera", "xfip", "csw_pct", "gb_pct", "hand", "innings_pitched", "starter_injured")
"""Columns `home`/`away` must carry, one row per game_id. `starter_injured`:
the probable pitcher's most recent point-in-time IL status (model doc §10.2's
"injury flag (starter + ...)"; the top-4-batters half of that flag lives in
`offense.py`, not here)."""


def compute_pitcher_features(home: pd.DataFrame, away: pd.DataFrame) -> pd.DataFrame:
    """`home`/`away` are indexed by game_id with `REQUIRED_COLUMNS`."""
    return _side_columns(home, "home").join(_side_columns(away, "away"), how="outer")


def _side_columns(side: pd.DataFrame, prefix: str) -> pd.DataFrame:
    value, used_fallback = _siera_with_xfip_fallback(side)
    return pd.DataFrame(
        {
            f"{prefix}_starter_siera": value,
            f"{prefix}_starter_siera_is_xfip_fallback": used_fallback,
            f"{prefix}_starter_csw_pct": side["csw_pct"],
            f"{prefix}_starter_gb_pct": side["gb_pct"],
            f"{prefix}_starter_hand": side["hand"],
            f"{prefix}_starter_injured": side["starter_injured"],
        },
        index=side.index,
    )


def _siera_with_xfip_fallback(side: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    small_sample = side["innings_pitched"].fillna(0) < SMALL_SAMPLE_INNINGS
    use_fallback = small_sample | side["siera"].isna()
    value = side["siera"].where(~use_fallback, side["xfip"])
    return value, use_fallback
