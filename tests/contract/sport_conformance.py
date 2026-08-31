"""Reusable `SportVertical`-protocol conformance checks.

`model`/`ingest` import `assert_sport_vertical_conforms` from their own test
suites once `sports/mlb/vertical.py` exists — this defines the check once so
every future sport vertical (NFL, NBA, ...) is held to the same bar.
`test_sport_conformance_harness.py` in this same directory self-tests this
module against a fake vertical, since no real one exists yet.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from numpy.random import default_rng

from sbm.contracts.feature import AsOf
from sbm.contracts.sport import SportVertical


def assert_sport_vertical_conforms(
    vertical: SportVertical, game_ids: list[str], *, n_draws: int = 1000
) -> None:
    """Run the full conformance suite for one `SportVertical` instance.

    `game_ids` must be ids the vertical's own `FeatureBuilder` can resolve —
    this suite can't invent fixture data for an arbitrary sport, so the
    caller supplies known-good ids.
    """
    assert isinstance(vertical, SportVertical), (
        f"{vertical!r} does not satisfy the SportVertical protocol"
    )
    assert vertical.key, "SportVertical.key must be a non-empty stable identifier"
    assert vertical.market_keys, "SportVertical.market_keys must be non-empty"
    for market_key in vertical.market_keys:
        assert isinstance(market_key, str) and market_key, "market_keys must be non-empty strings"

    as_of = AsOf(ts=datetime.now(UTC))
    builder = vertical.feature_builder()
    features = builder.build(game_ids, as_of)

    assert set(features.index) == set(game_ids), "FeatureBuilder.build must return one row per id"

    _assert_build_deterministic(builder, game_ids, as_of)
    _assert_distribution_conforms(vertical, features, n_draws)


def _assert_build_deterministic(builder, game_ids: list[str], as_of: AsOf) -> None:
    first = builder.build(game_ids, as_of)
    second = builder.build(game_ids, as_of)
    assert first.equals(second), "FeatureBuilder.build is not deterministic for (game_ids, as_of)"


def _assert_distribution_conforms(
    vertical: SportVertical, features: pd.DataFrame, n_draws: int
) -> None:
    for game_id, row in list(features.iterrows())[:3]:
        dist = vertical.distribution(row)
        assert dist.n_dims in (1, 2), f"Distribution.n_dims must be 1 or 2, got {dist.n_dims}"

        draws_a = dist.sample(n_draws, default_rng(seed=1))
        draws_b = dist.sample(n_draws, default_rng(seed=1))
        assert draws_a.shape == (n_draws, dist.n_dims), (
            f"sample() shape {draws_a.shape} != ({n_draws}, {dist.n_dims})"
        )
        assert (draws_a == draws_b).all(), (
            f"Distribution.sample for {game_id} is not deterministic given a fixed rng"
        )
