"""Fitting the calibrators a walk-forward fold applies (model doc A5).

Two decisions live here:

* **One calibrator per market key, not one pooled across markets.** A
  moneyline's miscalibration curve and a total's are different functions; a
  single pooled fit averages them into a curve that is right for neither.
  (Backend doc §3.3's "blended-only" `calibration_buckets` is a *reporting*
  grain — it does not say fit one curve.)
* **Fit on both sides of every settled market, not just the side we picked.**
  The picked side is the model's favourite, so its probabilities cluster in the
  upper half of [0, 1]; fitting on that sample alone would leave the lower half
  of the range uncalibrated even though the very next fold prices sides there.

Isotonic is the primary calibrator (A5). Below `MIN_ISOTONIC_ROWS` it chases
noise in a thin slice, so Platt's smoother sigmoid takes over — the fallback
`calibration/isotonic.py` already names. Below `MIN_CALIBRATION_ROWS` nothing
is fit and `raw_model_prob` passes through untouched, which is the honest state
early in a walk-forward rather than a calibration fitted on nothing. Both
thresholds are engineering defaults, not doc numbers, and are arguments so a
caller can re-tune them against real data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from sbm.contracts.market import Market
from sbm.core.backtest.scoring import RawProbs, quoted_lines
from sbm.core.backtest.settlement import settle
from sbm.core.backtest.types import BacktestGame
from sbm.core.calibration import Calibrator, IsotonicCalibrator, PlattCalibrator

MIN_CALIBRATION_ROWS = 50
"""Below this many settled rows a market is scored uncalibrated."""

MIN_ISOTONIC_ROWS = 250
"""Below this many rows Platt scaling replaces isotonic regression."""


def calibration_rows(
    games: Sequence[BacktestGame],
    raw_probs: RawProbs,
    markets: Mapping[str, Market],
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """`(raw_prob, won)` pairs per market key, over both sides of every game.

    Pushes are dropped: a push is not a binary outcome, and scoring it as a loss
    would drag every bucket's empirical rate below its true value and teach the
    calibrator to shade probabilities down.
    """
    raw: dict[str, list[float]] = {}
    won: dict[str, list[float]] = {}
    for game in games:
        for market_key, line in quoted_lines(game).items():
            market = markets[market_key]
            for side in market.sides:
                result = settle(market, side, line, game.outcome)
                if result == "push":
                    continue
                raw.setdefault(market_key, []).append(raw_probs[(game.game_id, market_key, side)])
                won.setdefault(market_key, []).append(1.0 if result == "win" else 0.0)
    return {
        key: (np.asarray(raw[key], dtype=np.float64), np.asarray(won[key], dtype=np.float64))
        for key in raw
    }


def fit_calibrators(
    games: Sequence[BacktestGame],
    raw_probs: RawProbs,
    markets: Mapping[str, Market],
    *,
    min_rows: int = MIN_CALIBRATION_ROWS,
    min_isotonic_rows: int = MIN_ISOTONIC_ROWS,
) -> dict[str, Calibrator]:
    """Calibrators for the markets with enough settled history to fit one.

    A market absent from the result is scored uncalibrated by design — callers
    must treat a missing key as pass-through, not as an error.
    """
    fitted: dict[str, Calibrator] = {}
    for market_key, (raw, won) in calibration_rows(games, raw_probs, markets).items():
        if len(raw) < min_rows or len(np.unique(won)) < 2:
            continue  # too thin, or single-class: nothing to learn, and sklearn would object
        cls = IsotonicCalibrator if len(raw) >= min_isotonic_rows else PlattCalibrator
        fitted[market_key] = cls.fit(raw, won)
    return fitted


def apply(calibrator: Calibrator | None, raw_prob: float) -> float:
    """One probability through one calibrator; pass-through when unfitted."""
    if calibrator is None:
        return raw_prob
    return float(calibrator.predict(np.asarray([raw_prob], dtype=np.float64))[0])
