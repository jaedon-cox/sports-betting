"""Shared call validation for `Market` implementations.

Not itself a market — a leading underscore keeps it out of the public
market-key surface (`sbm.markets.MARKETS`).
"""

from __future__ import annotations

from sbm.contracts.distribution import Draws


def validate_call(draws: Draws, side: str, sides: tuple[str, ...], required_dims: int) -> None:
    if side not in sides:
        raise ValueError(f"side must be one of {sides}, got {side!r}")
    if draws.ndim != 2 or draws.shape[1] != required_dims:
        raise ValueError(f"draws must have shape (n, {required_dims}), got {draws.shape}")
