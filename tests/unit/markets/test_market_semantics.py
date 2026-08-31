"""markets/: what each market actually means, beyond protocol conformance.

`tests/contract/test_markets.py` proves every market satisfies the protocol.
This file proves each one computes the right thing — the sign of a spread line,
which side a total's push falls on, that a prop reads column 0 — using draws
whose answer is known exactly.
"""

from __future__ import annotations

import numpy as np
import pytest

from sbm.markets import (
    MARKETS,
    MoneylineMarket,
    PropMarket,
    SpreadMarket,
    TotalMarket,
    market_registry,
)


def _draws(*rows: tuple[float, ...]) -> np.ndarray:
    return np.array(rows, dtype=np.float64)


def test_registry_keys_match_the_plugins() -> None:
    """Market keys are data persisted in `picks.market` (rule 7) — the registry
    key and the plugin's own key must never disagree."""
    assert all(key == cls.key for key, cls in MARKETS.items())
    assert set(MARKETS) == {"moneyline", "total", "spread", "prop"}


def test_market_registry_returns_instances() -> None:
    registry = market_registry()
    assert set(registry) == set(MARKETS)
    assert all(instance.key == key for key, instance in registry.items())


# --- moneyline -------------------------------------------------------------


def test_moneyline_counts_outright_wins() -> None:
    draws = _draws((5.0, 3.0), (2.0, 6.0), (4.0, 1.0), (0.0, 7.0))
    market = MoneylineMarket()
    assert market.probability(draws, "home", None) == 0.5
    assert market.probability(draws, "away", None) == 0.5


def test_moneyline_ignores_the_line() -> None:
    """`line` exists for protocol conformance only — a moneyline has none."""
    draws = _draws((5.0, 3.0), (2.0, 6.0))
    market = MoneylineMarket()
    assert market.probability(draws, "home", None) == market.probability(draws, "home", 1.5)


def test_moneyline_excludes_ties_from_both_sides() -> None:
    draws = _draws((4.0, 4.0), (5.0, 3.0))
    market = MoneylineMarket()
    assert market.probability(draws, "home", None) == 0.5
    assert market.probability(draws, "away", None) == 0.0


# --- total -----------------------------------------------------------------


def test_total_sums_both_columns() -> None:
    draws = _draws((5.0, 3.0), (2.0, 2.0), (6.0, 4.0))  # totals 8, 4, 10
    market = TotalMarket()
    assert market.probability(draws, "over", 8.5) == pytest.approx(1 / 3)
    assert market.probability(draws, "under", 8.5) == pytest.approx(2 / 3)


def test_total_pushes_on_an_exact_integer_line() -> None:
    draws = _draws((4.0, 4.0), (5.0, 4.0))  # totals 8, 9
    market = TotalMarket()
    assert market.probability(draws, "over", 8.0) == 0.5
    assert market.probability(draws, "under", 8.0) == 0.0


def test_total_requires_a_line() -> None:
    with pytest.raises(ValueError, match="requires a line"):
        TotalMarket().probability(_draws((5.0, 3.0)), "over", None)


# --- spread ----------------------------------------------------------------


def test_spread_line_is_written_from_the_home_perspective() -> None:
    """home -1.5 means the home margin must beat 1.5, and the away side is the
    exact complement of that — one shared number, not a sign-flipped pair
    (spread.py docstring)."""
    draws = _draws((5.0, 3.0), (4.0, 3.0), (2.0, 6.0))  # margins +2, +1, -4
    market = SpreadMarket()
    assert market.probability(draws, "home", -1.5) == pytest.approx(1 / 3)
    assert market.probability(draws, "away", -1.5) == pytest.approx(2 / 3)


def test_spread_handles_the_underdog_side_of_the_line() -> None:
    draws = _draws((5.0, 3.0), (4.0, 3.0), (2.0, 6.0))  # margins +2, +1, -4
    market = SpreadMarket()
    assert market.probability(draws, "home", 1.5) == pytest.approx(2 / 3)
    assert market.probability(draws, "away", 1.5) == pytest.approx(1 / 3)


def test_spread_pushes_on_an_exact_margin() -> None:
    draws = _draws((5.0, 3.0), (6.0, 3.0))  # margins +2, +3
    market = SpreadMarket()
    assert market.probability(draws, "home", -2.0) == 0.5
    assert market.probability(draws, "away", -2.0) == 0.0


def test_run_line_is_a_spread_not_its_own_market() -> None:
    """MLB's ±1.5 run-line is `SpreadMarket` at line -1.5 (CLAUDE.md) — there is
    deliberately no `run_line` key to look up."""
    assert "run_line" not in MARKETS


# --- prop ------------------------------------------------------------------


def test_prop_reads_a_single_stat_column() -> None:
    draws = _draws((5.0,), (7.0,), (6.0,))
    market = PropMarket()
    assert market.required_dims == 1
    assert market.probability(draws, "over", 5.5) == pytest.approx(2 / 3)
    assert market.probability(draws, "under", 5.5) == pytest.approx(1 / 3)


def test_prop_rejects_two_column_draws() -> None:
    """The dimension guard is what keeps a game distribution from being priced
    as a player prop by accident."""
    with pytest.raises(ValueError, match="shape"):
        PropMarket().probability(_draws((5.0, 3.0)), "over", 5.5)


def test_team_markets_reject_one_column_draws() -> None:
    for market in (MoneylineMarket(), TotalMarket(), SpreadMarket()):
        with pytest.raises(ValueError, match="shape"):
            market.probability(_draws((5.0,)), market.sides[0], 1.5)
