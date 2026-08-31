"""Team offense (model doc §10.2/§10.3): wRC+ plus platoon-adjusted xwOBA vs
the OPPOSING starter's handedness.

`wrc_plus`/`xwoba_vs_opp_hand` are season-to-date aggregates from
`ingest/pybaseball.py` (same "value as of the pull" caveat as
`pitcher.py`'s SIERA — no per-game team-offense time series is available to
EWMA over; doc §10.1's 15-20 game half-life is aspirational until a per-game
source exists). Platoon splits (vs-LHP / vs-RHP xwOBA) must be computed by
whoever supplies `xwoba_vs_opp_hand` — that split itself isn't in the
`statcast_batter_expected_stats` columns this repo verified at build time
(no handedness breakdown there); flagged as a gap alongside the EWMA one.
"""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = ("wrc_plus", "xwoba_vs_opp_hand", "key_injuries_count")
"""Columns `home`/`away` must carry, one row per game_id. `xwoba_vs_opp_hand`
is already resolved against the OPPOSING team's starter handedness — i.e.
`home`'s value already reflects `away`'s starter hand, and vice versa.

`key_injuries_count`: model doc §10.2's "injury flag (... + top-4)" wants the
top-4 *batting-order* players specifically — this repo has no lineup-order
ingest yet (see `builder.py`'s gap list), so this is a coarser proxy: count
of the team's 40-man roster position players currently IL-flagged
(`ingest/statsapi/roster.py`'s `is_injured`), not scoped to the actual top 4
in tonight's order. Flagged to `model` as an approximation, not the doc's
exact spec."""


def compute_offense_features(home: pd.DataFrame, away: pd.DataFrame) -> pd.DataFrame:
    """`home`/`away` are indexed by game_id with `REQUIRED_COLUMNS`."""
    return _side_columns(home, "home").join(_side_columns(away, "away"), how="outer")


def _side_columns(side: pd.DataFrame, prefix: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            f"{prefix}_off_wrc_plus": side["wrc_plus"],
            f"{prefix}_off_xwoba_vs_opp_hand": side["xwoba_vs_opp_hand"],
            f"{prefix}_off_key_injuries_count": side["key_injuries_count"],
        },
        index=side.index,
    )
