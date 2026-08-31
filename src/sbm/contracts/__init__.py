"""Frozen interfaces. Protocols and dataclasses only — never any logic.

Changing anything here changes every teammate's assumptions, so treat edits as
a contract renegotiation, not a refactor.
"""

from sbm.contracts.distribution import Distribution, Draws
from sbm.contracts.feature import AsOf, FeatureBuilder
from sbm.contracts.market import Market, MarketQuote
from sbm.contracts.sport import SportVertical

__all__ = [
    "AsOf",
    "Distribution",
    "Draws",
    "FeatureBuilder",
    "Market",
    "MarketQuote",
    "SportVertical",
]
