from __future__ import annotations

import pandas as pd

from sbm.sports.mlb.features.park import compute_park_features


def test_assembles_park_columns_and_flags_fixed_dome() -> None:
    park = pd.DataFrame(
        {
            "run_factor": [None, 1.04],
            "roof_type": ["Dome", "Open"],
            "turf_type": ["Artificial", "Grass"],
            "orientation_deg": [45.0, 9.0],
        },
        index=pd.Index(["g1", "g2"], name="game_id"),
    )
    out = compute_park_features(park)
    assert out.loc["g1", "park_is_fixed_dome"] == True  # noqa: E712
    assert out.loc["g2", "park_is_fixed_dome"] == False  # noqa: E712
    assert out.loc["g2", "park_run_factor"] == 1.04
    assert out.loc["g1", "park_orientation_deg"] == 45.0
