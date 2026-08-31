"""Reusable `Market`-protocol conformance checks.

Any `Market` implementation — the four in `sbm.markets` today, a sport-scoped
market in the future — must pass `assert_market_conforms`. Kept out of
`test_markets.py` so a future `sports/*` test suite can reuse it without
duplicating the checks.
"""

from __future__ import annotations

import numpy as np
from numpy.random import Generator

from sbm.contracts.market import Market


def assert_market_conforms(market: Market, rng: Generator, *, n_draws: int = 5000) -> None:
    """Run the full conformance suite for one `Market` instance."""
    assert isinstance(market, Market), f"{market!r} does not satisfy the Market protocol"
    assert len(market.sides) == 2, "conformance suite assumes exactly 2 complementary sides"

    _assert_probability_in_unit_interval(market, rng, n_draws)
    _assert_complementary_sides(market, rng, n_draws)
    _assert_push_excluded_from_both_sides(market)
    _assert_dimension_mismatch_raises(market, rng)
    _assert_invalid_side_raises(market, rng, n_draws)
    _assert_deterministic(market, rng, n_draws)


def _draws(market: Market, rng: Generator, n: int) -> np.ndarray:
    return rng.normal(loc=0.0, scale=1.0, size=(n, market.required_dims))


def _line_for(market: Market) -> float | None:
    return None if market.key == "moneyline" else 1.5


def _assert_probability_in_unit_interval(market: Market, rng: Generator, n: int) -> None:
    draws = _draws(market, rng, n)
    line = _line_for(market)
    for side in market.sides:
        p = market.probability(draws, side, line)
        assert 0.0 <= p <= 1.0, f"{market.key}/{side} probability {p} outside [0, 1]"


def _assert_complementary_sides(market: Market, rng: Generator, n: int) -> None:
    draws = _draws(market, rng, n)
    line = _line_for(market)
    total = sum(market.probability(draws, side, line) for side in market.sides)
    assert total <= 1.0 + 1e-9, f"{market.key} sides sum to {total} > 1"


def _assert_push_excluded_from_both_sides(market: Market, n: int = 8) -> None:
    """All-zero draws at `line=0.0` is a guaranteed exact-tie/push scenario for
    every market shape (equal team draws, zero total, zero margin, zero
    stat): both sides must report probability 0, not merely sum <= 1."""
    draws = np.zeros((n, market.required_dims))
    line = 0.0
    for side in market.sides:
        p = market.probability(draws, side, line)
        assert p == 0.0, f"{market.key}/{side} did not exclude the push, got p={p}"


def _assert_dimension_mismatch_raises(market: Market, rng: Generator) -> None:
    wrong_dims = market.required_dims + 1
    draws = rng.normal(size=(10, wrong_dims))
    try:
        market.probability(draws, market.sides[0], _line_for(market))
    except ValueError:
        return
    raise AssertionError(f"{market.key} did not raise on a draw-dimension mismatch")


def _assert_invalid_side_raises(market: Market, rng: Generator, n: int) -> None:
    draws = _draws(market, rng, n)
    try:
        market.probability(draws, "not_a_real_side", _line_for(market))
    except ValueError:
        return
    raise AssertionError(f"{market.key} did not raise on an invalid side")


def _assert_deterministic(market: Market, rng: Generator, n: int) -> None:
    draws = _draws(market, rng, n)
    line = _line_for(market)
    side = market.sides[0]
    first = market.probability(draws, side, line)
    second = market.probability(draws, side, line)
    assert first == second, f"{market.key} is not deterministic for identical draws"
