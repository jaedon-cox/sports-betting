"""odds_math.py: American <-> probability <-> decimal, and their invariants."""

from __future__ import annotations

import pytest

from sbm.core.pricing import (
    american_to_decimal_odds,
    american_to_implied_prob,
    implied_prob_to_american,
)


@pytest.mark.parametrize(
    ("price", "prob"),
    [(100, 0.5), (-100, 0.5), (-200, 2 / 3), (200, 1 / 3), (-110, 110 / 210)],
)
def test_implied_prob_matches_definition(price: int, prob: float) -> None:
    assert american_to_implied_prob(price) == pytest.approx(prob)


@pytest.mark.parametrize("price", [-100000, -500, -110, -101, 101, 110, 500, 100000])
def test_price_to_prob_round_trips(price: int) -> None:
    """implied_prob_to_american is the documented inverse — a drift here would
    silently change every persisted `market_odds_american`."""
    assert implied_prob_to_american(american_to_implied_prob(price)) == price


@pytest.mark.parametrize("prob", [0.05, 0.25, 0.4999, 0.5, 0.5001, 0.75, 0.95])
def test_prob_to_price_round_trips_within_rounding(prob: float) -> None:
    price = implied_prob_to_american(prob)
    assert american_to_implied_prob(price) == pytest.approx(prob, abs=5e-4)


@pytest.mark.parametrize("price", [-100000, -500, -110, 110, 500, 100000])
def test_decimal_odds_agree_with_implied_prob(price: int) -> None:
    """Decimal odds are 1/implied for a vig-free price, and Kelly's `b` term
    depends on that identity holding for both signs."""
    assert american_to_decimal_odds(price) == pytest.approx(1.0 / american_to_implied_prob(price))


def test_implied_prob_is_monotone_decreasing_in_price() -> None:
    prices = [-500, -200, -110, 110, 200, 500]
    probs = [american_to_implied_prob(p) for p in prices]
    assert probs == sorted(probs, reverse=True)


def test_even_money_is_the_pivot() -> None:
    assert american_to_implied_prob(100) == 0.5
    assert american_to_decimal_odds(100) == 2.0
    assert implied_prob_to_american(0.5) == -100


@pytest.mark.parametrize("bad", [0])
def test_zero_price_rejected(bad: int) -> None:
    with pytest.raises(ValueError):
        american_to_implied_prob(bad)
    with pytest.raises(ValueError):
        american_to_decimal_odds(bad)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.5])
def test_probability_outside_open_unit_interval_rejected(bad: float) -> None:
    with pytest.raises(ValueError):
        implied_prob_to_american(bad)
