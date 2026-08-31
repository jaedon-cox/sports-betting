"""MLB feature-row schema — the one place `vertical.py` depends on `ingest`'s exact
column names and raw units.

Schema confirmed by `ingest` (teammate message): home_/away_ prefixed per-side stats,
un-prefixed park/weather (park belongs to the home team; weather is shared). Values are
RAW stat scale (e.g. wRC+ centered on 100, SIERA centered on ~4.00), not pre-standardized
— this module does the centering/scaling so `mean.py`/`alpha.py` stay schema-agnostic
and receive roughly unit-scale inputs. League-average anchors below are rough public
priors, not fit — same "not yet earned empirically" status as the model coefficients
they feed (doc §6).

Two known gaps, not silently worked around (see ingest's message for the full list):
- No dedicated lineup-contact-quality column exists yet. `contact_quality_proxy` reuses
  this side's own standardized xwOBA-vs-opp-hand as a stand-in, which makes it
  collinear with `off_xwoba_z` (mean.py's batting term) — a real weakness, not a
  deliberate modeling choice. Asked `ingest` whether a dedicated batter contact%/
  hard-hit% column can be added; swap this the moment one exists.
- `park_run_factor` is null for most/all v1 games (ingest gap #1) — `park_factor_log`
  is 0.0 (neutral, not "average") whenever that's the case, so park contributes
  nothing to most games' mu until a real source lands.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from sbm.sports.mlb.model.environment import DEFAULT_WEATHER_MODEL, park_factor_log

WRC_PLUS_LEAGUE_AVG = 100.0
WRC_PLUS_SCALE = 15.0
SIERA_LEAGUE_AVG = 4.00
SIERA_SCALE = 0.60
XWOBA_LEAGUE_AVG = 0.320
XWOBA_SCALE = 0.025
XFIP_LEAGUE_AVG = 4.00
XFIP_SCALE = 0.60
CSW_PCT_LEAGUE_AVG = 0.28
GB_PCT_LEAGUE_AVG = 0.43


@dataclass(frozen=True, slots=True)
class SideInputs:
    """Everything one side's NB(mu, alpha) needs, already cross-referenced: a side's
    mean/dispersion depends on the OPPOSING side's pitching, not its own."""

    off_wrc_plus_z: float
    off_xwoba_z: float
    opp_starter_siera_z: float
    opp_bullpen_xfip_z: float
    opp_bullpen_fatigue_raw: float
    """Passthrough, not standardized: ingest flags `bullpen_fatigue`'s units as TBD
    until core's EWMA is wired — nothing to standardize against yet."""
    opp_starter_csw_pct: float
    """CSW%, not K% — the doc's actual v1 stack cuts standalone K% (§10.5) and keeps
    CSW% as the fast-stabilizing skill signal (§3.1); same directional role in
    alpha.py's dispersion model, different (real) column."""
    opp_starter_gb_pct: float
    contact_quality_proxy: float
    park_factor_log: float
    weather_run_factor_log: float
    is_home: bool


def _raw(features: pd.Series, name: str) -> float:
    """Raises only if the COLUMN itself is missing (schema mismatch); NaN values
    pass through for `_or_default` to handle as an expected data gap."""
    if name not in features:
        raise KeyError(
            f"expected feature column '{name}' — see model/columns.py; confirm "
            "naming with ingest before changing this file"
        )
    value = features[name]
    return float(value) if pd.notna(value) else float("nan")


def _or_default(features: pd.Series, name: str, default: float) -> float:
    """NaN-safe read: `ingest` marks many columns nullable (small-sample /
    missing-source games). Default to a neutral prior rather than raise, per doc
    §5.4's shrinkage discipline — "assume average" beats crashing the pipeline."""
    value = _raw(features, name)
    return default if np.isnan(value) else value


def _standardize(value: float, league_avg: float, scale: float) -> float:
    return (value - league_avg) / scale


def extract_side_inputs(features: pd.Series, side: str) -> SideInputs:
    """Build one side's model inputs from a game feature row.

    side='home': home team bats, away team pitches to them (and vice versa for
    side='away'). `contact_quality_proxy` is `side`'s own offense, since that's the
    lineup the OPPOSING starter (`opp`) actually faces — see module docstring for
    why this is a proxy, not a dedicated column.
    """
    if side not in ("home", "away"):
        raise ValueError(f"side must be 'home' or 'away', got {side!r}")
    opp = "away" if side == "home" else "home"

    off_wrc_plus = _or_default(features, f"off_wrc_plus_{side}", WRC_PLUS_LEAGUE_AVG)
    off_xwoba = _or_default(features, f"off_xwoba_vs_opp_hand_{side}", XWOBA_LEAGUE_AVG)
    opp_siera = _or_default(features, f"starter_siera_{opp}", SIERA_LEAGUE_AVG)
    opp_xfip = _or_default(features, f"bullpen_xfip_{opp}", XFIP_LEAGUE_AVG)
    opp_fatigue = _or_default(features, f"bullpen_fatigue_{opp}", 0.0)
    opp_csw = _or_default(features, f"starter_csw_pct_{opp}", CSW_PCT_LEAGUE_AVG)
    opp_gb = _or_default(features, f"starter_gb_pct_{opp}", GB_PCT_LEAGUE_AVG)

    return SideInputs(
        off_wrc_plus_z=_standardize(off_wrc_plus, WRC_PLUS_LEAGUE_AVG, WRC_PLUS_SCALE),
        off_xwoba_z=_standardize(off_xwoba, XWOBA_LEAGUE_AVG, XWOBA_SCALE),
        opp_starter_siera_z=_standardize(opp_siera, SIERA_LEAGUE_AVG, SIERA_SCALE),
        opp_bullpen_xfip_z=_standardize(opp_xfip, XFIP_LEAGUE_AVG, XFIP_SCALE),
        opp_bullpen_fatigue_raw=opp_fatigue,
        opp_starter_csw_pct=opp_csw,
        opp_starter_gb_pct=opp_gb,
        contact_quality_proxy=_standardize(off_xwoba, XWOBA_LEAGUE_AVG, XWOBA_SCALE),
        park_factor_log=park_factor_log(features.get("park_run_factor")),
        weather_run_factor_log=DEFAULT_WEATHER_MODEL.predict_log_factor(
            features.get("wind_out_component_mph"), features.get("temp_under_55")
        ),
        is_home=(side == "home"),
    )
