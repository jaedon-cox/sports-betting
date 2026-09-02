"""vertical.py: SportVertical conformance and feature-row -> distribution wiring."""

from __future__ import annotations

import numpy as np
import pandas as pd

from sbm.contracts.distribution import Distribution
from sbm.contracts.feature import FeatureBuilder
from sbm.contracts.sport import SportVertical
from sbm.sports.mlb.vertical import MLBVertical

GAME_ROW = pd.Series(
    {
        "home_off_wrc_plus": 115.0,
        "away_off_wrc_plus": 90.0,
        "home_off_xwoba_vs_opp_hand": 0.340,
        "away_off_xwoba_vs_opp_hand": 0.300,
        "home_starter_siera": 3.40,
        "away_starter_siera": 4.60,
        "home_bullpen_xfip": 3.70,
        "away_bullpen_xfip": 4.30,
        "home_bullpen_fatigue": 0.6,
        "away_bullpen_fatigue": -0.4,
        "home_starter_csw_pct": 0.31,
        "away_starter_csw_pct": 0.25,
        "home_starter_gb_pct": 0.48,
        "away_starter_gb_pct": 0.38,
        "park_run_factor": 1.05,
        "wind_out_component_mph": 5.0,
        "temp_under_55": False,
    }
)


def test_satisfies_sport_vertical_protocol() -> None:
    vertical = MLBVertical()
    assert isinstance(vertical, SportVertical)
    assert vertical.key == "mlb"
    assert vertical.market_keys == ("moneyline", "total", "spread")


def test_distribution_from_feature_row_is_sampleable_and_2d() -> None:
    dist = MLBVertical().distribution(GAME_ROW)
    assert isinstance(dist, Distribution)
    assert dist.n_dims == 2
    draws = dist.sample(1000, np.random.default_rng(0))
    assert draws.shape == (1000, 2)
    assert np.all(draws >= 0)


def test_distribution_never_sees_market_odds_columns() -> None:
    """A1: market odds are never a model input. A row with an odds-shaped column
    should have no effect on distribution() since it's never read."""
    row_with_odds = GAME_ROW.copy()
    row_with_odds["market_fair_prob_home"] = 0.9  # should be ignored, not consumed
    dist_a = MLBVertical().distribution(GAME_ROW)
    dist_b = MLBVertical().distribution(row_with_odds)
    assert dist_a.home == dist_b.home
    assert dist_a.away == dist_b.away


def test_feature_builder_is_constructible_and_conforms() -> None:
    """`ingest` has shipped `MLBFeatureBuilder` (deferred-imported by `vertical.py`
    so this works the moment it exists, without vertical.py itself ever failing to
    import). Its `.build()` still raises until `db` wires a real point-in-time
    snapshot source (documented, not silently worked around) — this test only
    checks the builder itself is constructible and protocol-conformant, not that
    `.build()` succeeds end to end, since that's outside model/'s territory.
    """
    builder = MLBVertical().feature_builder()
    assert isinstance(builder, FeatureBuilder)
