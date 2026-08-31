"""Wind x park-orientation interaction — model doc §3.7's flagged **primary
weather alpha**: "does wind blow out to the actual fences of *this* park?"
is harder for the market to price than raw wind speed alone.

**Convention assumed (flag if wrong):** `park_orientation_deg` is the bearing
from home plate toward dead center field (MLB StatsAPI's `azimuthAngle` —
this repo's read of that field's exact meaning is unverified against MLB's
own docs; see `ingest/statsapi/venue.py`). `wind_dir_deg` follows
meteorological convention — the direction wind is blowing FROM (Open-Meteo's
default) — so the wind's travel bearing is `wind_dir_deg + 180`.

`wind_out_component_mph`: signed mph of wind blowing toward center field
along the park's own axis — positive carries fly balls out (favors
runs/totals), negative suppresses them. Raw wind speed alone is doc-CUT
(§10.5) precisely because it's mostly priced; this computed projection is
the mispricing candidate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TEMP_COLD_THRESHOLD_F = 55.0
"""Below this, doc §3.7 flags reduced carry as a real, cheap-to-compute
effect worth keeping even though raw temperature alone is a weak signal."""

REQUIRED_COLUMNS = ("wind_mph", "wind_dir_deg", "temp_f", "precip_pct", "park_orientation_deg")
"""Columns `weather` must carry, one row per game_id — the forecast already
resolved to each game's start hour by `builder.py`; this module does no
time-of-game matching itself."""


def compute_weather_features(weather: pd.DataFrame) -> pd.DataFrame:
    blowing_toward_deg = (weather["wind_dir_deg"] + 180.0) % 360.0
    angle_from_cf = np.radians(blowing_toward_deg - weather["park_orientation_deg"])
    wind_out_component = weather["wind_mph"] * np.cos(angle_from_cf)
    return pd.DataFrame(
        {
            "wind_out_component_mph": wind_out_component,
            "temp_f": weather["temp_f"],
            "temp_under_55": weather["temp_f"] < TEMP_COLD_THRESHOLD_F,
            "precip_pct": weather["precip_pct"],
        },
        index=weather.index,
    )
