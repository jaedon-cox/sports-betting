"""Predicted mean runs per side — the mu half of each game's NB(mu, alpha).

Pairs with `alpha.py`'s dispersion model. mu is a log-linear combination of the
batting side's offense quality and the OPPOSING side's pitching/bullpen quality, so
home and away mu come from calling `predict` twice with the sides swapped (see
`vertical.py`) — this module never shares state across sides, so one side's runs
can't silently leak into the other's mean.

Inputs are the standardized/passthrough values `columns.py` produces from ingest's
real feature frame — wRC+ and xwOBA are kept as SEPARATE terms (not one combined
"batting quality") because the doc treats them as complementary, not redundant
(§3.4: "xwOBA adds the deserved-vs-actual mispricing angle on top of wRC+").

Coefficients are directional priors, not fit — same "earn it empirically" discipline
as `alpha.py` (model doc §6); replace once games settle and a real regression exists.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

LEAGUE_AVG_RUNS_PER_GAME = 4.5
"""Rough per-team run-scoring baseline; an intercept anchor only, not fit."""


@dataclass(frozen=True, slots=True)
class MeanRunsModel:
    """log(mu) = intercept + the terms below, each a standardized (or passthrough)
    scalar from `columns.py` — see that module for the raw-to-standardized mapping.
    """

    intercept: float = float(np.log(LEAGUE_AVG_RUNS_PER_GAME))
    coef_off_wrc_plus: float = 0.15
    """Batting side's park/platoon-adjusted wRC+ (standardized)."""
    coef_off_xwoba: float = 0.15
    """Batting side's xwOBA vs the opposing starter's hand (standardized) — adds
    the "deserved vs actual" signal on top of wRC+, not a substitute for it."""
    coef_opp_starter_siera: float = 0.35
    """Opposing STARTER's SIERA (standardized so higher = worse pitcher = more runs)."""
    coef_opp_bullpen_xfip: float = 0.15
    """Opposing bullpen's skill (xFIP, standardized so higher = worse = more runs)."""
    coef_opp_bullpen_fatigue: float = 0.05
    """Opposing bullpen fatigue/usage — the doc's primary bullpen alpha hypothesis
    (§3.2). Small default weight: ingest flags this column's units as a TBD
    passthrough placeholder pending core's EWMA, so there's no real scale to
    calibrate a coefficient against yet — revisit once that lands."""
    coef_park_factor: float = 1.0
    """Park run factor is already a runs-scale multiplier on log-mu from ingest."""
    coef_weather_run_factor: float = 1.0
    """Computed wind x orientation / cold-temp run-environment adjustment, already
    log-scale from `environment.py` (doc §3.7's primary weather alpha candidate)."""
    home_field_log_bump: float = 0.02
    """Small, well-known offensive edge for the batting-last side."""

    def predict(
        self,
        off_wrc_plus_z: pd.Series | np.ndarray | float,
        off_xwoba_z: pd.Series | np.ndarray | float,
        opp_starter_siera_z: pd.Series | np.ndarray | float,
        opp_bullpen_xfip_z: pd.Series | np.ndarray | float,
        opp_bullpen_fatigue_raw: pd.Series | np.ndarray | float,
        park_factor_log: pd.Series | np.ndarray | float,
        weather_run_factor_log: pd.Series | np.ndarray | float,
        is_home: bool | np.ndarray,
    ) -> np.ndarray:
        """Vectorized mu for one or many (batting-side, pitching-side) rows."""
        log_mu = (
            self.intercept
            + self.coef_off_wrc_plus * np.asarray(off_wrc_plus_z, dtype=np.float64)
            + self.coef_off_xwoba * np.asarray(off_xwoba_z, dtype=np.float64)
            + self.coef_opp_starter_siera * np.asarray(opp_starter_siera_z, dtype=np.float64)
            + self.coef_opp_bullpen_xfip * np.asarray(opp_bullpen_xfip_z, dtype=np.float64)
            + self.coef_opp_bullpen_fatigue * np.asarray(opp_bullpen_fatigue_raw, dtype=np.float64)
            + self.coef_park_factor * np.asarray(park_factor_log, dtype=np.float64)
            + self.coef_weather_run_factor * np.asarray(weather_run_factor_log, dtype=np.float64)
            + self.home_field_log_bump * np.asarray(is_home, dtype=np.float64)
        )
        return np.exp(log_mu)

    def predict_one(
        self,
        off_wrc_plus_z: float,
        off_xwoba_z: float,
        opp_starter_siera_z: float,
        opp_bullpen_xfip_z: float,
        opp_bullpen_fatigue_raw: float,
        park_factor_log: float,
        weather_run_factor_log: float,
        is_home: bool,
    ) -> float:
        """Scalar convenience wrapper around `predict` for single-game callers."""
        return float(
            self.predict(
                off_wrc_plus_z,
                off_xwoba_z,
                opp_starter_siera_z,
                opp_bullpen_xfip_z,
                opp_bullpen_fatigue_raw,
                park_factor_log,
                weather_run_factor_log,
                is_home,
            )
        )


DEFAULT_MEAN_MODEL = MeanRunsModel()
