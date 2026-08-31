"""MLB-side calibration wiring (model doc A5; db doc `picks.raw_model_prob` vs
`picks.model_prob`).

Thin policy wrapper around `core.calibration`: fit only on the `calibration`
slice of a `core.calibration.chronological_split` (A5 — never `train`, and
never `test`, which stays untouched for reporting), and always keep the
pre-calibration probability alongside the calibrated one for drift monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from sbm.core.calibration import Calibrator, ChronoSplit, IsotonicCalibrator


@dataclass(frozen=True, slots=True)
class CalibratedProbabilities:
    """Both numbers `db` persists — `raw_model_prob` for drift monitoring,
    `model_prob` for edge/Kelly. Never collapse these into one column."""

    raw_model_prob: NDArray[np.float64]
    model_prob: NDArray[np.float64]


def fit_calibrator_on_split(
    split: ChronoSplit,
    raw_prob: NDArray[np.float64],
    outcome: NDArray[np.float64],
    *,
    calibrator_cls: type = IsotonicCalibrator,
) -> Calibrator:
    """Fit strictly on `split.calibration` — never `split.train` or `split.test` (A5).

    Taking the whole `ChronoSplit` rather than a bare boolean mask means a future
    edit at a call site can't accidentally swap in `train` or `test`; this
    function decides which mask to use, once, in the one place that matters.
    """
    mask = split.calibration
    return calibrator_cls.fit(raw_prob[mask], outcome[mask])


def apply_calibration(
    calibrator: Calibrator | None, raw_model_prob: NDArray[np.float64]
) -> CalibratedProbabilities:
    """Pass-through (`model_prob == raw_model_prob`) if no calibrator is fit yet —
    the honest state before enough settled games exist for A5's later-slice split.
    """
    raw = np.asarray(raw_model_prob, dtype=np.float64)
    calibrated = raw if calibrator is None else np.asarray(calibrator.predict(raw), dtype=np.float64)
    return CalibratedProbabilities(raw_model_prob=raw, model_prob=calibrated)
