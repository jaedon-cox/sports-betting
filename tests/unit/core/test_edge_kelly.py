"""edge.py + kelly.py: sizing invariants.

Kelly is where a probability becomes money, so the properties that matter are
structural — zero at zero edge, monotone in edge, never negative, never more
than the bankroll — not any particular hand-computed number.
"""

from __future__ import annotations

import pytest

from sbm.core.pricing import (
    DEFAULT_KELLY_FRACTION,
    american_to_implied_prob,
    edge_pct,
    full_kelly_fraction,
    kelly_stake_fraction,
)

PRICES = [-320, -150, -110, 110, 150, 260]


def test_edge_is_the_signed_difference() -> None:
    assert edge_pct(0.55, 0.50) == pytest.approx(0.05)
    assert edge_pct(0.45, 0.50) == pytest.approx(-0.05)
    assert edge_pct(0.5, 0.5) == 0.0


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_edge_rejects_non_probabilities(bad: float) -> None:
    with pytest.raises(ValueError):
        edge_pct(bad, 0.5)
    with pytest.raises(ValueError):
        edge_pct(0.5, bad)


@pytest.mark.parametrize("price", PRICES)
def test_full_kelly_is_zero_at_the_break_even_probability(price: int) -> None:
    """Break-even is the price's own implied prob — no vig-free edge, no stake."""
    breakeven = american_to_implied_prob(price)
    assert full_kelly_fraction(breakeven, price) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("price", PRICES)
def test_full_kelly_is_strictly_increasing_in_model_probability(price: int) -> None:
    breakeven = american_to_implied_prob(price)
    stakes = [full_kelly_fraction(min(breakeven + d, 0.999), price) for d in (0.0, 0.02, 0.05, 0.1)]
    assert stakes == sorted(stakes)
    assert stakes[0] < stakes[-1]


@pytest.mark.parametrize("price", PRICES)
def test_full_kelly_goes_negative_without_an_edge(price: int) -> None:
    assert full_kelly_fraction(american_to_implied_prob(price) - 0.05, price) < 0.0


@pytest.mark.parametrize("price", PRICES)
def test_stake_is_clamped_to_zero_when_there_is_no_edge(price: int) -> None:
    """A negative full-Kelly means "don't bet", never "bet the other side"."""
    assert kelly_stake_fraction(american_to_implied_prob(price) - 0.05, price) == 0.0


@pytest.mark.parametrize("price", PRICES)
def test_stake_is_the_configured_fraction_of_full_kelly(price: int) -> None:
    prob = min(american_to_implied_prob(price) + 0.08, 0.99)
    expected = DEFAULT_KELLY_FRACTION * full_kelly_fraction(prob, price)
    assert kelly_stake_fraction(prob, price) == pytest.approx(expected)


def test_default_fraction_is_the_decided_quarter_kelly() -> None:
    assert DEFAULT_KELLY_FRACTION == 0.25


def test_stake_never_exceeds_the_bankroll() -> None:
    """A pathological certainty must not size past 100% of bankroll."""
    assert kelly_stake_fraction(1.0, 100, fraction=1.0) == 1.0
    assert 0.0 <= kelly_stake_fraction(0.999, -100000, fraction=1.0) <= 1.0


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.5])
def test_invalid_kelly_fraction_rejected(bad: float) -> None:
    with pytest.raises(ValueError):
        kelly_stake_fraction(0.6, 100, fraction=bad)


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_kelly_rejects_non_probabilities(bad: float) -> None:
    with pytest.raises(ValueError):
        full_kelly_fraction(bad, 100)


@pytest.mark.parametrize("price", PRICES)
def test_stake_scales_as_edge_over_one_minus_breakeven(price: int) -> None:
    """Full Kelly reduces to `edge / (1 - break_even_prob)`, which is why the
    same absolute edge is worth more on a short price than a long one — sizing
    reads the price on offer, not the fair price (kelly.py docstring)."""
    breakeven = american_to_implied_prob(price)
    edge = 0.03
    assert full_kelly_fraction(breakeven + edge, price) == pytest.approx(edge / (1.0 - breakeven))
