"""environment.py: park/weather translation into the log-scale run-factor terms."""

from __future__ import annotations

import math

from sbm.sports.mlb.model.environment import DEFAULT_WEATHER_MODEL, park_factor_log


def test_park_factor_log_neutral_when_none() -> None:
    assert park_factor_log(None) == 0.0


def test_park_factor_log_neutral_when_nan() -> None:
    assert park_factor_log(float("nan")) == 0.0


def test_park_factor_log_neutral_when_nonpositive() -> None:
    assert park_factor_log(0.0) == 0.0
    assert park_factor_log(-1.0) == 0.0


def test_park_factor_log_matches_log_when_present() -> None:
    assert park_factor_log(1.1) == math.log(1.1)


def test_wind_blowing_out_raises_weather_factor() -> None:
    calm = DEFAULT_WEATHER_MODEL.predict_log_factor(0.0, False)
    blowing_out = DEFAULT_WEATHER_MODEL.predict_log_factor(10.0, False)
    assert blowing_out > calm


def test_cold_temperature_lowers_weather_factor() -> None:
    warm = DEFAULT_WEATHER_MODEL.predict_log_factor(0.0, False)
    cold = DEFAULT_WEATHER_MODEL.predict_log_factor(0.0, True)
    assert cold < warm


def test_weather_factor_handles_missing_inputs() -> None:
    assert DEFAULT_WEATHER_MODEL.predict_log_factor(None, None) == 0.0
    assert DEFAULT_WEATHER_MODEL.predict_log_factor(float("nan"), None) == 0.0
