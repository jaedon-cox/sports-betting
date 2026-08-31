from __future__ import annotations

import pandas as pd

from sbm.sports.mlb.features.bullpen import compute_bullpen_features


def test_assembles_home_and_away_bullpen_columns() -> None:
    home = pd.DataFrame(
        {"fatigue": [42.0], "xfip": [3.9], "unavailable_arms": [1]},
        index=pd.Index(["g1"], name="game_id"),
    )
    away = pd.DataFrame(
        {"fatigue": [15.0], "xfip": [4.4], "unavailable_arms": [0]},
        index=pd.Index(["g1"], name="game_id"),
    )
    out = compute_bullpen_features(home, away)
    assert out.loc["g1", "home_bullpen_fatigue"] == 42.0
    assert out.loc["g1", "away_bullpen_xfip"] == 4.4
    assert out.loc["g1", "home_bullpen_unavailable_arms"] == 1
