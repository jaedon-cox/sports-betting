"""backtest/calibrate.py: what the walk-forward fits, and on what.

Three decisions get asserted here because each is easy to regress silently:
per-market fits, both sides in the fit set, and pushes excluded from it.
"""

from __future__ import annotations

import numpy as np
from conftest import START, make_game
from numpy.random import default_rng

from sbm.core.backtest import (
    MIN_CALIBRATION_ROWS,
    calibration_rows,
    fit_calibrators,
    raw_probabilities,
)
from sbm.core.backtest.calibrate import apply
from sbm.core.calibration import IsotonicCalibrator, PlattCalibrator


def _moneyline_games(n: int) -> list:
    return [
        make_game(f"g{i:03d}", ts=START, outcome=(5.0, 3.0) if i % 2 else (2.0, 6.0))
        for i in range(n)
    ]


def test_rows_cover_both_sides_of_every_game(vertical, markets: dict) -> None:
    """Fitting on the picked side only would leave the lower half of the
    probability range uncalibrated (module docstring)."""
    games = _moneyline_games(4)
    probs = raw_probabilities(vertical, markets, games, n_draws=500, rng=default_rng(0))
    raw, won = calibration_rows(games, probs, markets)["moneyline"]
    assert len(raw) == 8
    assert set(won) == {0.0, 1.0}


def test_rows_are_grouped_per_market(vertical, markets: dict) -> None:
    games = [
        make_game("g001", ts=START),
        make_game(
            "g002",
            ts=START,
            market="total",
            line=8.5,
            bet={"over": -110, "under": -110},
            close={"over": -110, "under": -110},
        ),
    ]
    probs = raw_probabilities(vertical, markets, games, n_draws=500, rng=default_rng(0))
    rows = calibration_rows(games, probs, markets)
    assert set(rows) == {"moneyline", "total"}
    assert all(len(raw) == 2 for raw, _ in rows.values())


def test_pushes_are_dropped_from_the_fit(vertical, markets: dict) -> None:
    """A push has no binary outcome; scoring it as a loss would teach the
    calibrator to shade every probability down."""
    game = make_game(
        "g001",
        ts=START,
        market="total",
        line=8.0,
        bet={"over": -110, "under": -110},
        close={"over": -110, "under": -110},
        outcome=(5.0, 3.0),
    )
    probs = raw_probabilities(vertical, markets, [game], n_draws=500, rng=default_rng(0))
    assert calibration_rows([game], probs, markets) == {}


def test_too_little_history_fits_nothing(vertical, markets: dict) -> None:
    """The honest early-walk-forward state: a missing key means pass-through,
    not an error."""
    games = _moneyline_games(4)
    probs = raw_probabilities(vertical, markets, games, n_draws=500, rng=default_rng(0))
    assert fit_calibrators(games, probs, markets) == {}


def test_both_sides_keep_a_lopsided_history_two_class(vertical, markets: dict) -> None:
    """Even a season where the home team always wins yields both labels, because
    the away side of each game is in the fit set too — a one-sided fit set would
    be single-class here and nothing would be learnable."""
    games = [make_game(f"g{i:03d}", ts=START, outcome=(9.0, 0.0)) for i in range(60)]
    probs = raw_probabilities(vertical, markets, games, n_draws=200, rng=default_rng(0))
    _, won = calibration_rows(games, probs, markets)["moneyline"]
    assert set(won) == {0.0, 1.0}
    assert "moneyline" in fit_calibrators(games, probs, markets, min_rows=10)


def test_platt_below_the_isotonic_threshold(vertical, markets: dict) -> None:
    games = _moneyline_games(40)
    probs = raw_probabilities(vertical, markets, games, n_draws=200, rng=default_rng(0))
    fitted = fit_calibrators(games, probs, markets, min_rows=10, min_isotonic_rows=1000)
    assert isinstance(fitted["moneyline"], PlattCalibrator)


def test_isotonic_above_the_threshold(vertical, markets: dict) -> None:
    games = _moneyline_games(40)
    probs = raw_probabilities(vertical, markets, games, n_draws=200, rng=default_rng(0))
    fitted = fit_calibrators(games, probs, markets, min_rows=10, min_isotonic_rows=10)
    assert isinstance(fitted["moneyline"], IsotonicCalibrator)


def test_default_thresholds_are_ordered() -> None:
    from sbm.core.backtest import MIN_ISOTONIC_ROWS

    assert MIN_CALIBRATION_ROWS < MIN_ISOTONIC_ROWS


def test_apply_passes_through_without_a_calibrator() -> None:
    assert apply(None, 0.37) == 0.37


def test_apply_returns_a_scalar_probability() -> None:
    raw = np.linspace(0.1, 0.9, 40)
    fitted = IsotonicCalibrator.fit(raw, (raw > 0.5).astype(float))
    value = apply(fitted, 0.8)
    assert isinstance(value, float)
    assert 0.0 <= value <= 1.0
