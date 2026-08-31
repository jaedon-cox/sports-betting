"""Park + weather translation into the log-scale run-factor terms `mean.py` needs.

`ingest` already resolves the "computed wind x park orientation" interaction (doc
§3.7's primary weather alpha candidate) into `wind_out_component_mph` — this module
only turns that, plus the cold-weather flag, into one log-scale multiplier on mu.
Coefficients are directional priors, not fit — same discipline as `alpha.py`/`mean.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def park_factor_log(park_run_factor: float | None) -> float:
    """log(park_run_factor) if present and positive, else 0.0 (neutral).

    `ingest` reports `park_run_factor` is null for most/all games in v1 — no free
    numeric park-factor source exists yet (their gap #1) — so 0.0 ("no
    information") is the honest default, not a guessed average-park value, and
    this term is a no-op for most games until that source lands.
    """
    if park_run_factor is None or not np.isfinite(park_run_factor) or park_run_factor <= 0:
        return 0.0
    return float(np.log(park_run_factor))


@dataclass(frozen=True, slots=True)
class WeatherModel:
    """log(weather_run_factor) = coef_wind * wind_out_mph + coef_cold * temp_under_55.

    Wind blowing OUT (positive component, per ingest's sign convention) carries
    the ball -> more runs. Sub-55F suppresses offense (doc §10.3) -> fewer runs.
    `precip_pct` isn't wired in: the doc's kept weather stack is wind + cold-temp
    only (§10.3); humidity/precip weren't in the locked v1 feature set (§10.5).
    """

    coef_wind_out_mph: float = 0.01
    coef_temp_under_55: float = -0.04

    def predict_log_factor(
        self, wind_out_component_mph: float | None, temp_under_55: bool | None
    ) -> float:
        wind = (
            0.0
            if wind_out_component_mph is None or not np.isfinite(wind_out_component_mph)
            else float(wind_out_component_mph)
        )
        cold = bool(temp_under_55) if temp_under_55 is not None else False
        return self.coef_wind_out_mph * wind + self.coef_temp_under_55 * float(cold)


DEFAULT_WEATHER_MODEL = WeatherModel()
