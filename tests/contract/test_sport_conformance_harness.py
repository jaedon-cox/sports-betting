"""Self-test for `sport_conformance.py` using an in-repo fake vertical.

Proves the reusable harness is correct *before* `model`/`ingest` build a real
`sports/mlb/vertical.py` against it — a bug here would silently pass any real
sport forever.
"""

from __future__ import annotations

import pandas as pd
import pytest
from numpy.random import Generator
from sport_conformance import assert_sport_vertical_conforms

from sbm.contracts.feature import AsOf, FeatureBuilder


class _FakeFeatureBuilder:
    def build(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame:
        return pd.DataFrame({"strength": [0.5] * len(game_ids)}, index=game_ids)


class _FakeDistribution:
    n_dims = 2

    def sample(self, n: int, rng: Generator):
        return rng.normal(loc=4.5, scale=2.0, size=(n, self.n_dims))


class _FakeVertical:
    key = "fake"
    market_keys = ("moneyline",)

    def feature_builder(self) -> FeatureBuilder:
        return _FakeFeatureBuilder()

    def distribution(self, features: pd.Series):
        return _FakeDistribution()


@pytest.mark.contract
def test_fake_vertical_conforms() -> None:
    assert_sport_vertical_conforms(_FakeVertical(), ["g1", "g2", "g3"])
