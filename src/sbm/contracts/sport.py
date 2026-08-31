"""What a sport must provide to plug into the engine.

Adding NFL/NBA means adding `sports/<sport>/vertical.py` satisfying this
protocol. Everything in `core/` and `markets/` then works unchanged.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd

from sbm.contracts.distribution import Distribution
from sbm.contracts.feature import FeatureBuilder


@runtime_checkable
class SportVertical(Protocol):
    """The seam between sport-specific modeling and the shared engine."""

    key: str
    """Stable identifier persisted in `picks.sport` — e.g. 'mlb'."""

    market_keys: tuple[str, ...]
    """Markets this vertical can price, matching `Market.key` values."""

    def feature_builder(self) -> FeatureBuilder:
        """Point-in-time feature source for this sport."""
        ...

    def distribution(self, features: pd.Series) -> Distribution:
        """Predictive distribution for one entity from one built feature row.

        For team markets `features` is a game row and the result has n_dims 2.
        For props it is a player-game row and the result has n_dims 1.
        """
        ...
