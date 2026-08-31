"""Park context (model doc §10.2/§10.3): run factor + roof + the structural
facts `features/weather.py` needs for the wind x orientation interaction.

`run_factor` is expected to be mostly null in v1 — neither MLB StatsAPI nor
pybaseball expose a numeric park run-factor source on the free tier
(pybaseball's `park_codes()` is broken upstream, and there is no numeric
park-factor function in the library at all — confirmed at build time,
flagged to `main`). Roof type / turf type / orientation ARE real, sourced
live from `ingest/statsapi/venue.py` (MLB's own `azimuthAngle`/`fieldInfo`),
not hardcoded.

**Retractable-roof caveat:** `roof_type` is the park's *structural* category
(Open/Dome/Retractable), not today's actual roof state — a retractable roof
may be open or closed on any given game day, and that's a separate,
game-day-specific fact this static venue fetch cannot provide. Only
`park_is_fixed_dome` (permanently enclosed) is safe to treat as certain;
weather features should be treated as lower-confidence, not automatically
inapplicable, for a `Retractable` park until that gap is closed.

No explicit "home flag" column: this frame is one row per game with
`home_`/`away_` prefixed columns throughout (see `builder.py`), so home-field
advantage is already structurally distinguishable without a redundant flag.
"""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = ("run_factor", "roof_type", "turf_type", "orientation_deg")
"""Columns `park` must carry, one row per game_id — the park belongs to the
home team, so there is no home/away split here."""


def compute_park_features(park: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "park_run_factor": park["run_factor"],
            "park_roof_type": park["roof_type"],
            "park_is_fixed_dome": park["roof_type"] == "Dome",
            "park_turf_type": park["turf_type"],
            "park_orientation_deg": park["orientation_deg"],
        },
        index=park.index,
    )
