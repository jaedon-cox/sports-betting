"""Walk-forward backtest: score point-in-time, calibrate forward, report CLV.

`run_backtest` is the entry point; the modules under it are the four steps it
composes — `scoring` (features -> draws -> probabilities), `calibrate` (fit on
strictly earlier settled rows), `evaluate` (de-vig, edge, Kelly, CLV) and
`report` (CLV gate, calibration, ROI-as-noise).
"""

from sbm.core.backtest.calibrate import (
    MIN_CALIBRATION_ROWS,
    MIN_ISOTONIC_ROWS,
    calibration_rows,
    fit_calibrators,
)
from sbm.core.backtest.engine import DEFAULT_N_DRAWS, DEFAULT_N_FOLDS, run_backtest
from sbm.core.backtest.evaluate import evaluate_game
from sbm.core.backtest.report import (
    ROI_MIN_BETS,
    BacktestReport,
    CalibrationSummary,
    ClvSummary,
    RoiSummary,
    calibration_summary,
    clv_summary,
    roi_summary,
    summarize,
)
from sbm.core.backtest.scoring import RawProbs, quoted_lines, raw_probabilities
from sbm.core.backtest.settlement import Settlement, settle
from sbm.core.backtest.types import BacktestGame, EvaluatedPick

__all__ = [
    "DEFAULT_N_DRAWS",
    "DEFAULT_N_FOLDS",
    "MIN_CALIBRATION_ROWS",
    "MIN_ISOTONIC_ROWS",
    "ROI_MIN_BETS",
    "BacktestGame",
    "BacktestReport",
    "CalibrationSummary",
    "ClvSummary",
    "EvaluatedPick",
    "RawProbs",
    "RoiSummary",
    "Settlement",
    "calibration_rows",
    "calibration_summary",
    "clv_summary",
    "evaluate_game",
    "fit_calibrators",
    "quoted_lines",
    "raw_probabilities",
    "roi_summary",
    "run_backtest",
    "settle",
    "summarize",
]
