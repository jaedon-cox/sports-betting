"""The walk-forward backtest loop.

**The split.** `calibration/splits.py` cuts the chronologically ordered games
three ways, and each slice has exactly one job (model doc A5):

    train        the sport model's own fitting window. Never scored here —
                 scoring it would report in-sample probabilities.
    calibration  seeds the calibrator. Later than `train` and held out from it,
                 which is the whole content of A5.
    test         the only slice reported. Walked forward in `n_folds` blocks.

**The walk forward.** Fold 0 is scored by a calibrator fit on the `calibration`
slice alone. Fold k is scored by a calibrator refit on that slice plus every
earlier fold — all of it settled, all of it strictly earlier than the rows being
scored. That is what production actually does (recalibrate on everything settled
to date), and it means no pick is ever priced by a calibrator that has seen its
own outcome or any later one.

**Determinism.** Every game is scored in one chronological pass *before* the
folds are cut, so the Monte-Carlo draws depend on the seed and the game order
and not on how the walk-forward is parameterized: changing `n_folds` changes
which calibrator a pick gets, never its draws. `rng` is threaded explicitly, so
a run reproduces exactly (CLAUDE.md conventions).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from numpy.random import Generator

from sbm.contracts.market import Market
from sbm.contracts.sport import SportVertical
from sbm.core.backtest.calibrate import MIN_CALIBRATION_ROWS, MIN_ISOTONIC_ROWS, fit_calibrators
from sbm.core.backtest.evaluate import evaluate_game
from sbm.core.backtest.report import BacktestReport, summarize
from sbm.core.backtest.scoring import raw_probabilities
from sbm.core.backtest.types import BacktestGame
from sbm.core.calibration import chronological_split
from sbm.core.pricing import DEFAULT_KELLY_FRACTION

DEFAULT_N_DRAWS = 100_000
"""Draws per game (backend doc §2.2). Vectorized, so a full slate is seconds."""

DEFAULT_N_FOLDS = 4
"""Walk-forward blocks across the test slice. More folds recalibrate more often
and shrink each fold's calibration-staleness at the cost of thinner fits."""


def run_backtest(
    vertical: SportVertical,
    games: Sequence[BacktestGame],
    *,
    markets: Mapping[str, Market],
    devig_method: str,
    rng: Generator,
    n_draws: int = DEFAULT_N_DRAWS,
    n_folds: int = DEFAULT_N_FOLDS,
    train_frac: float = 0.6,
    calibration_frac: float = 0.2,
    edge_threshold: float = 0.0,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    min_calibration_rows: int = MIN_CALIBRATION_ROWS,
    min_isotonic_rows: int = MIN_ISOTONIC_ROWS,
) -> BacktestReport:
    """Walk `games` forward chronologically and report CLV, calibration and ROI.

    `markets` maps market key -> plugin instance (e.g.
    `sbm.markets.market_registry()`); it is passed in rather than imported so
    `core` depends on the `Market` contract and not on which markets exist —
    market keys are data, not enums (rule 7).

    `devig_method` is required: it must be the method locked for these markets,
    identical at open and at close, or the CLV number is part method artifact
    (`pricing/devig.py`).
    """
    if not games:
        raise ValueError("backtest needs at least one game")
    if n_folds < 1:
        raise ValueError(f"n_folds must be >= 1, got {n_folds}")

    ordered = sorted(games, key=lambda g: (g.as_of.ts, g.game_id))
    raw_probs = raw_probabilities(vertical, markets, ordered, n_draws=n_draws, rng=rng)

    split = chronological_split(
        [game.as_of.ts for game in ordered],
        train_frac=train_frac,
        calibration_frac=calibration_frac,
    )
    seed_games = [game for game, keep in zip(ordered, split.calibration, strict=True) if keep]
    test_games = [game for game, keep in zip(ordered, split.test, strict=True) if keep]

    picks = []
    for fold_index, block in enumerate(_folds(len(test_games), n_folds)):
        history = seed_games + test_games[: block[0]]
        calibrators = fit_calibrators(
            history,
            raw_probs,
            markets,
            min_rows=min_calibration_rows,
            min_isotonic_rows=min_isotonic_rows,
        )
        for game in test_games[block[0] : block[-1] + 1]:
            picks.extend(
                evaluate_game(
                    game,
                    raw_probs,
                    markets,
                    calibrators,
                    devig_method=devig_method,
                    fold=fold_index,
                    edge_threshold=edge_threshold,
                    kelly_fraction=kelly_fraction,
                )
            )

    return summarize(
        picks,
        n_games_scored=len(test_games),
        n_games_excluded=len(ordered) - len(test_games),
    )


def _folds(n_test: int, n_folds: int) -> list[list[int]]:
    """Contiguous, chronologically ordered index blocks over the test slice.

    Empty blocks are dropped so a test slice shorter than `n_folds` degrades to
    fewer folds rather than raising — a short backtest is still a backtest.
    """
    return [block.tolist() for block in np.array_split(np.arange(n_test), n_folds) if block.size]
