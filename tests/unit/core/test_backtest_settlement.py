"""backtest/settlement.py: a bet settles under the rule that priced it.

The design claim being tested is that no market needs settlement code of its
own — feeding the final score through the plugin as a single draw is enough,
including for the push cases.
"""

from __future__ import annotations

import numpy as np
import pytest

from sbm.core.backtest import settle
from sbm.markets import MoneylineMarket, PropMarket, SpreadMarket, TotalMarket


def _result(*values: float) -> np.ndarray:
    return np.array([values], dtype=np.float64)


def test_moneyline_settles_on_the_final_score() -> None:
    market = MoneylineMarket()
    assert settle(market, "home", None, _result(5.0, 3.0)) == "win"
    assert settle(market, "away", None, _result(5.0, 3.0)) == "loss"


def test_total_settles_over_and_under() -> None:
    market = TotalMarket()
    assert settle(market, "over", 8.5, _result(5.0, 4.0)) == "win"
    assert settle(market, "under", 8.5, _result(5.0, 4.0)) == "loss"


def test_total_push_on_an_exact_integer_line() -> None:
    """Both sides read 0.0 — the protocol's push, recognised without a special
    case per market."""
    market = TotalMarket()
    assert settle(market, "over", 9.0, _result(5.0, 4.0)) == "push"
    assert settle(market, "under", 9.0, _result(5.0, 4.0)) == "push"


def test_spread_settles_from_the_home_perspective() -> None:
    market = SpreadMarket()
    assert settle(market, "home", -1.5, _result(5.0, 3.0)) == "win"
    assert settle(market, "home", -1.5, _result(4.0, 3.0)) == "loss"
    assert settle(market, "away", -1.5, _result(4.0, 3.0)) == "win"


def test_spread_push_on_an_exact_margin() -> None:
    assert settle(SpreadMarket(), "home", -2.0, _result(5.0, 3.0)) == "push"


def test_prop_settles_from_one_column() -> None:
    market = PropMarket()
    assert settle(market, "over", 6.5, _result(7.0)) == "win"
    assert settle(market, "under", 6.5, _result(7.0)) == "loss"
    assert settle(market, "over", 7.0, _result(7.0)) == "push"


def test_settlement_is_exhaustive_over_both_sides() -> None:
    """Whatever the result, exactly one of {win, loss} holds for one side and
    the mirror for the other — or both push."""
    market = TotalMarket()
    for total_line in (7.5, 8.0, 8.5, 9.0):
        over = settle(market, "over", total_line, _result(5.0, 4.0))
        under = settle(market, "under", total_line, _result(5.0, 4.0))
        assert {over, under} in ({"win", "loss"}, {"push"})


def test_multi_row_outcome_rejected() -> None:
    """A backtest settles against one realized game, not a sample of them."""
    with pytest.raises(ValueError, match="single realized row"):
        settle(MoneylineMarket(), "home", None, np.array([[5.0, 3.0], [2.0, 1.0]]))


def test_unknown_side_rejected() -> None:
    with pytest.raises(ValueError):
        settle(MoneylineMarket(), "over", None, _result(5.0, 3.0))
