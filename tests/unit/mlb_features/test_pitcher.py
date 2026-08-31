from __future__ import annotations

import pandas as pd

from sbm.sports.mlb.features.pitcher import compute_pitcher_features


def _frame(*, n: int = 1, **cols: list) -> pd.DataFrame:
    cols.setdefault("starter_injured", [False] * n)
    return pd.DataFrame(cols, index=pd.Index([f"g{i + 1}" for i in range(n)], name="game_id"))


def test_uses_siera_when_sample_is_large_enough() -> None:
    home = _frame(
        n=2, siera=[3.1, 3.4], xfip=[3.5, 3.9], csw_pct=[0.30, 0.28],
        gb_pct=[0.45, 0.40], hand=["R", "L"], innings_pitched=[120.0, 150.0],
    )
    away = _frame(
        n=2, siera=[4.0, 3.6], xfip=[4.2, 3.7], csw_pct=[0.27, 0.29],
        gb_pct=[0.38, 0.42], hand=["L", "R"], innings_pitched=[100.0, 110.0],
        starter_injured=[False, True],
    )
    out = compute_pitcher_features(home, away)
    assert out.loc["g1", "home_starter_siera"] == 3.1
    assert out.loc["g1", "home_starter_siera_is_xfip_fallback"] == False  # noqa: E712
    assert out.loc["g2", "away_starter_injured"] == True  # noqa: E712


def test_falls_back_to_xfip_under_small_sample_threshold() -> None:
    home = _frame(siera=[2.8], xfip=[3.9], csw_pct=[0.31], gb_pct=[0.44], hand=["R"], innings_pitched=[12.0])
    away = _frame(siera=[3.9], xfip=[4.0], csw_pct=[0.27], gb_pct=[0.38], hand=["L"], innings_pitched=[110.0])
    out = compute_pitcher_features(home, away)
    assert out.loc["g1", "home_starter_siera"] == 3.9  # xFIP, not the noisy SIERA
    assert out.loc["g1", "home_starter_siera_is_xfip_fallback"] == True  # noqa: E712


def test_falls_back_to_xfip_when_siera_is_missing() -> None:
    home = _frame(siera=[None], xfip=[4.1], csw_pct=[0.30], gb_pct=[0.40], hand=["R"], innings_pitched=[140.0])
    away = _frame(siera=[3.9], xfip=[4.0], csw_pct=[0.27], gb_pct=[0.38], hand=["L"], innings_pitched=[110.0])
    out = compute_pitcher_features(home, away)
    assert out.loc["g1", "home_starter_siera"] == 4.1
    assert out.loc["g1", "home_starter_siera_is_xfip_fallback"] == True  # noqa: E712


def test_carries_handedness_and_csw_gb_columns_through() -> None:
    home = _frame(siera=[3.1], xfip=[3.5], csw_pct=[0.30], gb_pct=[0.45], hand=["R"], innings_pitched=[120.0])
    away = _frame(siera=[4.0], xfip=[4.2], csw_pct=[0.27], gb_pct=[0.38], hand=["L"], innings_pitched=[100.0])
    out = compute_pitcher_features(home, away)
    assert out.loc["g1", "home_starter_hand"] == "R"
    assert out.loc["g1", "away_starter_csw_pct"] == 0.27
    assert out.loc["g1", "away_starter_gb_pct"] == 0.38
