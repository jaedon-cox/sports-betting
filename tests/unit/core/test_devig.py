"""devig.py: every method must return a fair distribution, and `method` must
never be optional — a method that can drift between open and close turns CLV
into a method artifact (module docstring)."""

from __future__ import annotations

import pytest

from sbm.core.pricing import (
    american_to_implied_prob,
    devig,
    devig_additive,
    devig_multiplicative,
    devig_power,
    devig_shin,
    devig_sides,
    recommended_method,
)

METHODS = ("multiplicative", "power", "additive", "shin")
BOOKS = [(-110, -110), (-150, 130), (-320, 260), (-110, -105), (140, -160)]


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("prices", BOOKS)
def test_fair_probs_sum_to_one(method: str, prices: tuple[int, int]) -> None:
    assert sum(devig(prices, method=method)) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("prices", BOOKS)
def test_fair_probs_are_probabilities(method: str, prices: tuple[int, int]) -> None:
    assert all(0.0 < p < 1.0 for p in devig(prices, method=method))


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("prices", BOOKS)
def test_devig_preserves_the_favourite(method: str, prices: tuple[int, int]) -> None:
    """De-vig removes overround; it must never reorder who is favoured."""
    raw = [american_to_implied_prob(p) for p in prices]
    fair = devig(prices, method=method)
    assert (raw[0] > raw[1]) == (fair[0] > fair[1])


@pytest.mark.parametrize("method", METHODS)
def test_vig_free_book_is_a_fixed_point(method: str) -> None:
    """A book already summing to 1 has nothing to strip, whatever the method."""
    assert devig((100, -100), method=method) == pytest.approx([0.5, 0.5], abs=1e-9)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("prices", BOOKS)
def test_every_method_shrinks_every_side(method: str, prices: tuple[int, int]) -> None:
    """Overround is positive on a real book, so fair < raw on both sides."""
    raw = [american_to_implied_prob(p) for p in prices]
    assert all(f <= r + 1e-12 for f, r in zip(devig(prices, method=method), raw, strict=True))


def test_power_corrects_the_favourite_more_than_proportional() -> None:
    """The reason power is the production seed: at a skewed price it does not
    shave both sides by the same constant factor (module docstring)."""
    prices = (-320, 260)
    power = devig_power(prices)
    multiplicative = devig_multiplicative(prices)
    assert power[0] != pytest.approx(multiplicative[0], abs=1e-6)


def test_additive_is_the_documented_two_way_closed_form() -> None:
    """`fair_fav = (raw_fav - raw_dog + 1) / 2` — the identity the docstring
    leans on to argue additive can never go negative for a 2-way book."""
    raw_fav, raw_dog = american_to_implied_prob(-320), american_to_implied_prob(260)
    assert devig_additive((-320, 260))[0] == pytest.approx((raw_fav - raw_dog + 1.0) / 2.0)


def test_additive_rejects_a_negative_share_on_a_three_way_book() -> None:
    """The guard the docstring calls defensive: unreachable for the 2-way books
    this system prices, reachable once a third outcome is a real longshot."""
    with pytest.raises(ValueError, match="non-positive"):
        devig_additive((-115, -115, 100000))


def test_shin_recovers_an_informed_money_split() -> None:
    fair = devig_shin((-150, 130))
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)
    assert fair[0] > fair[1]


def test_method_is_required_and_validated() -> None:
    with pytest.raises(TypeError):
        devig((-110, -110))  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="unknown de-vig method"):
        devig((-110, -110), method="vibes")


def test_devig_needs_a_complementary_pair() -> None:
    with pytest.raises(ValueError, match="at least two"):
        devig((-110,), method="power")


def test_devig_sides_keeps_the_side_mapping() -> None:
    fair = devig_sides({"home": -150, "away": 130}, method="power")
    assert set(fair) == {"home", "away"}
    assert fair["home"] > fair["away"]
    assert sum(fair.values()) == pytest.approx(1.0, abs=1e-9)
    assert fair == devig_sides({"away": 130, "home": -150}, method="power")


def test_recommended_method_switches_on_skew() -> None:
    """Configuration-time helper only; the threshold is the doc's 0.20 spread."""
    assert recommended_method((-110, -110)) == "multiplicative"
    assert recommended_method((-320, 260)) == "power"
