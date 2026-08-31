from __future__ import annotations

import pandas as pd

from sbm.sports.mlb.features.tto import compute_tto_features


def test_bullpen_exposure_is_remaining_innings_after_starter() -> None:
    home = pd.DataFrame({"expected_ip": [5.5], "scheduled_innings": [9]}, index=pd.Index(["g1"], name="game_id"))
    away = pd.DataFrame({"expected_ip": [6.2], "scheduled_innings": [9]}, index=pd.Index(["g1"], name="game_id"))
    out = compute_tto_features(home, away)
    assert out.loc["g1", "home_bullpen_exposure_ip"] == 3.5
    assert out.loc["g1", "away_bullpen_exposure_ip"] == 2.8


def test_bullpen_exposure_never_goes_negative() -> None:
    # A starter projected to go the full (or extra) distance in a shortened game.
    home = pd.DataFrame({"expected_ip": [8.0], "scheduled_innings": [7]}, index=pd.Index(["g1"], name="game_id"))
    away = pd.DataFrame({"expected_ip": [5.0], "scheduled_innings": [7]}, index=pd.Index(["g1"], name="game_id"))
    out = compute_tto_features(home, away)
    assert out.loc["g1", "home_bullpen_exposure_ip"] == 0.0
