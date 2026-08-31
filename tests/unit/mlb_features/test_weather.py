"""Sign/magnitude of wind_out_component_mph against known cardinal cases —
this is the doc's flagged primary alpha, so getting the vector math backwards
would silently invert the signal for every totals/run-line pick."""

from __future__ import annotations

import pytest
import pandas as pd

from sbm.sports.mlb.features.weather import compute_weather_features


def _row(wind_mph: float, wind_dir_deg: float, orientation_deg: float = 0.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "wind_mph": [wind_mph],
            "wind_dir_deg": [wind_dir_deg],
            "temp_f": [70.0],
            "precip_pct": [0.0],
            "park_orientation_deg": [orientation_deg],
        },
        index=pd.Index(["g1"], name="game_id"),
    )


def test_wind_from_behind_home_plate_blows_straight_out_to_cf() -> None:
    # CF faces due north (orientation 0). Wind FROM due south blows toward CF.
    out = compute_weather_features(_row(wind_mph=10.0, wind_dir_deg=180.0, orientation_deg=0.0))
    assert out.loc["g1", "wind_out_component_mph"] == pytest.approx(10.0)


def test_wind_from_center_field_blows_straight_in() -> None:
    # Wind FROM due north (same direction as CF) blows toward home plate.
    out = compute_weather_features(_row(wind_mph=10.0, wind_dir_deg=0.0, orientation_deg=0.0))
    assert out.loc["g1", "wind_out_component_mph"] == pytest.approx(-10.0)


def test_pure_crosswind_has_no_out_in_component() -> None:
    out = compute_weather_features(_row(wind_mph=10.0, wind_dir_deg=90.0, orientation_deg=0.0))
    assert out.loc["g1", "wind_out_component_mph"] == pytest.approx(0.0, abs=1e-9)


def test_temp_under_55_flag() -> None:
    weather = pd.DataFrame(
        {
            "wind_mph": [0.0, 0.0],
            "wind_dir_deg": [0.0, 0.0],
            "temp_f": [50.0, 60.0],
            "precip_pct": [0.0, 0.0],
            "park_orientation_deg": [0.0, 0.0],
        },
        index=pd.Index(["g1", "g2"], name="game_id"),
    )
    out = compute_weather_features(weather)
    assert out.loc["g1", "temp_under_55"] == True  # noqa: E712
    assert out.loc["g2", "temp_under_55"] == False  # noqa: E712
