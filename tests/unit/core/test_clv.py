"""clv.py: the gate metric's sign convention and units.

Getting the sign backwards here would invert the one number the whole system is
optimized for, so the direction is asserted explicitly rather than implied.
"""

from __future__ import annotations

import pytest

from sbm.core.clv import compute_clv


def test_positive_when_the_market_moves_toward_the_bet() -> None:
    """The side's fair prob rose after the bet -> the price taken beat the close."""
    assert compute_clv(bet_prob=0.50, closing_prob=0.55).clv_pct > 0


def test_negative_when_the_market_moves_away() -> None:
    assert compute_clv(bet_prob=0.55, closing_prob=0.50).clv_pct < 0


def test_zero_when_the_line_does_not_move() -> None:
    result = compute_clv(bet_prob=0.5, closing_prob=0.5)
    assert result.clv_pct == 0.0
    assert result.clv_bps == 0.0


def test_pct_is_relative_to_the_bet_price() -> None:
    assert compute_clv(bet_prob=0.50, closing_prob=0.55).clv_pct == pytest.approx(0.10)
    assert compute_clv(bet_prob=0.25, closing_prob=0.275).clv_pct == pytest.approx(0.10)


def test_bps_is_pct_in_basis_points() -> None:
    result = compute_clv(bet_prob=0.50, closing_prob=0.505)
    assert result.clv_bps == pytest.approx(result.clv_pct * 10_000.0)
    assert result.clv_bps == pytest.approx(100.0)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.2])
def test_probabilities_must_be_devigged_fair_probs(bad: float) -> None:
    """Raw (vig-inclusive) implied probs can exceed 1 as a pair, but neither
    side is ever <= 0 or >= 1 once de-vigged — an out-of-range input means the
    caller skipped `pricing/devig.py`."""
    with pytest.raises(ValueError):
        compute_clv(bet_prob=bad, closing_prob=0.5)
    with pytest.raises(ValueError):
        compute_clv(bet_prob=0.5, closing_prob=bad)
