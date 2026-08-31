"""MLB vertical — the seam satisfying `contracts/sport.py`.

Wires `ingest`'s feature frame into `model/`'s NB run-distribution. Every number
here is either read straight from a feature row (via `model/columns.py`) or produced
by the pure numeric models in `model/mean.py`/`model/alpha.py` — this file itself
carries no modeling logic, only wiring, so it stays a thin plugin per the doc's
"markets are separate from sports" seam.
"""

from __future__ import annotations

import pandas as pd

from sbm.contracts.distribution import Distribution
from sbm.contracts.feature import FeatureBuilder
from sbm.sports.mlb.model.alpha import DEFAULT_ALPHA_MODEL
from sbm.sports.mlb.model.columns import extract_side_inputs
from sbm.sports.mlb.model.mean import DEFAULT_MEAN_MODEL
from sbm.sports.mlb.model.nb import NBParams, NegativeBinomialRunDistribution

MARKET_KEYS: tuple[str, ...] = ("moneyline", "total", "spread")
"""Matches the `Market.key` values `core` actually defines in `markets/` (doc
§4/§10.4: all three derive from the same NB joint distribution — no per-market
model). NOTE: core's file is `markets/spread.py` with `key = "spread"`, while the
db doc's schema locks `picks.market CHECK IN ('moneyline','total','run_line')` and
the model doc calls this market "run-line" throughout (§10.4). Using "spread" here
to match core's actual shipped code; flagged to `core`/`main` as a naming
inconsistency to resolve before `db`'s CHECK constraint is written."""

FITTED_COPULA_RHO: float | None = None
"""No fitted residual correlation exists yet — `model/independence.py`'s test needs
settled games to run, and none exist in this build. None -> `nb.py` draws home/away
independently, the honest default until proven otherwise (doc §10.6: independence is
tested first, never assumed)."""


class MLBVertical:
    """Satisfies `contracts.sport.SportVertical` for MLB."""

    key = "mlb"
    market_keys = MARKET_KEYS

    def feature_builder(self) -> FeatureBuilder:
        # Deferred import: `ingest` owns this module and it may not exist yet in
        # every checkout state; keeping the import here means importing `vertical`
        # itself never fails on that, only actually calling this method does.
        from sbm.sports.mlb.features import MLBFeatureBuilder

        return MLBFeatureBuilder()

    def distribution(self, features: pd.Series) -> Distribution:
        """One game row in, one joint (home, away) NB distribution out.

        Market odds never appear on `features` (A1, enforced by `contracts/feature
        .py`'s `FeatureBuilder`) and this method never computes a market
        probability itself — `core.markets` turns these draws into P(side wins |
        line), not this vertical.
        """
        home = _side_params(features, "home")
        away = _side_params(features, "away")
        return NegativeBinomialRunDistribution(home=home, away=away, rho=FITTED_COPULA_RHO)


def _side_params(features: pd.Series, side: str) -> NBParams:
    inputs = extract_side_inputs(features, side)
    mu = DEFAULT_MEAN_MODEL.predict_one(
        off_wrc_plus_z=inputs.off_wrc_plus_z,
        off_xwoba_z=inputs.off_xwoba_z,
        opp_starter_siera_z=inputs.opp_starter_siera_z,
        opp_bullpen_xfip_z=inputs.opp_bullpen_xfip_z,
        opp_bullpen_fatigue_raw=inputs.opp_bullpen_fatigue_raw,
        park_factor_log=inputs.park_factor_log,
        weather_run_factor_log=inputs.weather_run_factor_log,
        is_home=inputs.is_home,
    )
    alpha = DEFAULT_ALPHA_MODEL.predict_one(
        csw_pct=inputs.opp_starter_csw_pct,
        gb_pct=inputs.opp_starter_gb_pct,
        contact_quality=inputs.contact_quality_proxy,
    )
    return NBParams(mu=mu, alpha=alpha)
