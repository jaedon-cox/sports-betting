"""Settling a bet by replaying the market plugin over the realized result.

A bet settles under exactly the rule that priced it, so there is no per-market
settlement branch to keep in sync with `markets/`: feed the final score in as a
single "draw" and the market's own probability collapses to 1.0 (this side
covered) or 0.0. Both sides reading 0.0 is precisely the push the `Market`
protocol already excludes from each side. Adding a market therefore adds no
settlement code — the same property that makes `markets/` pluggable.

'void' (backend doc §3.2's fourth outcome) is a scheduling fact — postponed,
cancelled — that a result row cannot express, so callers drop those games
before they reach here.
"""

from __future__ import annotations

from typing import Literal

from sbm.contracts.distribution import Draws
from sbm.contracts.market import Market

Settlement = Literal["win", "loss", "push"]


def settle(market: Market, side: str, line: float | None, outcome: Draws) -> Settlement:
    """How `side` at `line` finished, given the realized `outcome` row.

    `outcome` is one row in the same column layout the market prices — (home,
    away) runs for a team market, one stat value for a prop.
    """
    if outcome.ndim != 2 or outcome.shape[0] != 1:
        raise ValueError(
            f"outcome must be a single realized row of shape (1, n), got {outcome.shape}"
        )
    if market.probability(outcome, side, line) == 1.0:
        return "win"
    if market.probability(outcome, opposite_side(market, side), line) == 1.0:
        return "loss"
    return "push"


def opposite_side(market: Market, side: str) -> str:
    """The complementary side, from `Market.sides`' documented complementary order."""
    if len(market.sides) != 2:
        raise ValueError(f"{market.key} has {len(market.sides)} sides; settlement assumes 2")
    if side not in market.sides:
        raise ValueError(f"side must be one of {market.sides}, got {side!r}")
    first, second = market.sides
    return second if side == first else first
