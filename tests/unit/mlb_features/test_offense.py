from __future__ import annotations

import pandas as pd

from sbm.sports.mlb.features.offense import compute_offense_features


def test_assembles_home_and_away_offense_columns() -> None:
    home = pd.DataFrame(
        {"wrc_plus": [112], "xwoba_vs_opp_hand": [0.335], "key_injuries_count": [0]},
        index=pd.Index(["g1"], name="game_id"),
    )
    away = pd.DataFrame(
        {"wrc_plus": [98], "xwoba_vs_opp_hand": [0.310], "key_injuries_count": [2]},
        index=pd.Index(["g1"], name="game_id"),
    )
    out = compute_offense_features(home, away)
    assert out.loc["g1", "home_off_wrc_plus"] == 112
    assert out.loc["g1", "away_off_xwoba_vs_opp_hand"] == 0.310
    assert out.loc["g1", "away_off_key_injuries_count"] == 2
