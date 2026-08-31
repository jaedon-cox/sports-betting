"""columns.py: feature-row extraction, home/away cross-referencing, NaN handling,
and standardization against ingest's real (raw-scale) schema."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sbm.sports.mlb.model.columns import (
    SIERA_LEAGUE_AVG,
    SIERA_SCALE,
    WRC_PLUS_LEAGUE_AVG,
    WRC_PLUS_SCALE,
    extract_side_inputs,
)

ROW = pd.Series(
    {
        "off_wrc_plus_home": 115.0,
        "off_wrc_plus_away": 90.0,
        "off_xwoba_vs_opp_hand_home": 0.340,
        "off_xwoba_vs_opp_hand_away": 0.300,
        "starter_siera_home": 3.40,
        "starter_siera_away": 4.60,
        "bullpen_xfip_home": 3.70,
        "bullpen_xfip_away": 4.30,
        "bullpen_fatigue_home": 0.6,
        "bullpen_fatigue_away": -0.4,
        "starter_csw_pct_home": 0.31,
        "starter_csw_pct_away": 0.25,
        "starter_gb_pct_home": 0.48,
        "starter_gb_pct_away": 0.38,
        "park_run_factor": 1.05,
        "wind_out_component_mph": 5.0,
        "temp_under_55": False,
    }
)


def test_home_side_uses_away_pitching_and_home_batting() -> None:
    inputs = extract_side_inputs(ROW, "home")
    assert inputs.off_wrc_plus_z == pytest.approx(
        (ROW["off_wrc_plus_home"] - WRC_PLUS_LEAGUE_AVG) / WRC_PLUS_SCALE
    )
    assert inputs.opp_starter_siera_z == pytest.approx(
        (ROW["starter_siera_away"] - SIERA_LEAGUE_AVG) / SIERA_SCALE
    )
    assert inputs.opp_bullpen_xfip_z != 0.0
    assert inputs.opp_bullpen_fatigue_raw == ROW["bullpen_fatigue_away"]
    assert inputs.opp_starter_csw_pct == ROW["starter_csw_pct_away"]
    assert inputs.opp_starter_gb_pct == ROW["starter_gb_pct_away"]
    assert inputs.is_home is True


def test_away_side_uses_home_pitching_and_away_batting() -> None:
    inputs = extract_side_inputs(ROW, "away")
    assert inputs.opp_starter_csw_pct == ROW["starter_csw_pct_home"]
    assert inputs.opp_starter_gb_pct == ROW["starter_gb_pct_home"]
    assert inputs.is_home is False


def test_contact_quality_proxy_uses_own_side_xwoba() -> None:
    """Documented proxy: this side's own standardized xwOBA, since that's the
    lineup the OPPOSING starter actually faces."""
    inputs_home = extract_side_inputs(ROW, "home")
    inputs_away = extract_side_inputs(ROW, "away")
    assert inputs_home.contact_quality_proxy == inputs_home.off_xwoba_z
    assert inputs_away.contact_quality_proxy == inputs_away.off_xwoba_z
    assert inputs_home.contact_quality_proxy != inputs_away.contact_quality_proxy


def test_invalid_side_raises() -> None:
    with pytest.raises(ValueError):
        extract_side_inputs(ROW, "neutral")


def test_missing_column_raises_keyerror() -> None:
    incomplete = ROW.drop("starter_siera_away")
    with pytest.raises(KeyError):
        extract_side_inputs(incomplete, "home")


def test_nan_value_defaults_instead_of_raising() -> None:
    """Ingest marks many columns nullable — a present-but-NaN value must default
    to a neutral prior, not crash the pipeline (doc §5.4 shrinkage discipline)."""
    row = ROW.copy()
    row["starter_siera_away"] = np.nan
    inputs = extract_side_inputs(row, "home")
    assert inputs.opp_starter_siera_z == 0.0  # standardized league-average default


def test_missing_shared_park_weather_columns_default_neutral() -> None:
    """park_run_factor / wind / temp are looked up via `.get()` — absent entirely
    (not just NaN) must still degrade gracefully to the neutral 0.0 factor."""
    row = ROW.drop(["park_run_factor", "wind_out_component_mph", "temp_under_55"])
    inputs = extract_side_inputs(row, "home")
    assert inputs.park_factor_log == 0.0
    assert inputs.weather_run_factor_log == 0.0
