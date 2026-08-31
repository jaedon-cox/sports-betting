"""What a market is: draws + a line + a side -> a probability.

Adding a market (props, alt lines, first-5-innings) means adding one file to
`markets/` that satisfies this protocol. It must never import from `sbm.sports`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sbm.contracts.distribution import Draws


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """A price offered by a book, as captured in a line snapshot."""

    market: str
    """Market key, matching `Market.key`."""
    side: str
    """'home' | 'away' | 'over' | 'under' — validated by the market plugin."""
    line: float | None
    """Total or spread number; None for moneyline."""
    price_american: int
    book: str = "pinnacle"


@runtime_checkable
class Market(Protocol):
    """Turns model draws into P(side wins | line)."""

    key: str
    """Stable identifier persisted in `picks.market`."""

    required_dims: int
    """Draw width this market consumes — 2 for team markets, 1 for props."""

    sides: tuple[str, ...]
    """Legal `side` values, in complementary order."""

    def probability(self, draws: Draws, side: str, line: float | None) -> float:
        """P(`side` covers `line`) under `draws`.

        Pushes are excluded from both sides, so `p(side) + p(opposite) <= 1`
        whenever an exact tie with the line is possible.
        """
        ...
