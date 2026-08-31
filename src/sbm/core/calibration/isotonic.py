"""Probability calibration: isotonic regression and Platt (logistic) scaling.

Both must be fit on the calibration slice only (`splits.py` / model doc A5)
and applied at inference to `raw_model_prob`, producing `picks.model_prob`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


@runtime_checkable
class Calibrator(Protocol):
    """A fitted probability calibrator."""

    def predict(self, raw_prob: NDArray[np.float64]) -> NDArray[np.float64]: ...


@dataclass(slots=True)
class IsotonicCalibrator:
    """Monotonic, non-parametric — the primary calibrator. Handles miscalibration
    shapes (e.g. non-sigmoid) that Platt scaling can't."""

    _model: IsotonicRegression

    @classmethod
    def fit(
        cls, raw_prob: NDArray[np.float64], outcome: NDArray[np.float64]
    ) -> IsotonicCalibrator:
        model = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        model.fit(raw_prob, outcome)
        return cls(_model=model)

    def predict(self, raw_prob: NDArray[np.float64]) -> NDArray[np.float64]:
        return self._model.predict(raw_prob)


@dataclass(slots=True)
class PlattCalibrator:
    """Sigmoid (logistic) calibration — a smoother, lower-variance fallback for
    a calibration slice too small for isotonic to be stable."""

    _model: LogisticRegression

    @classmethod
    def fit(cls, raw_prob: NDArray[np.float64], outcome: NDArray[np.float64]) -> PlattCalibrator:
        model = LogisticRegression()
        model.fit(raw_prob.reshape(-1, 1), outcome)
        return cls(_model=model)

    def predict(self, raw_prob: NDArray[np.float64]) -> NDArray[np.float64]:
        return self._model.predict_proba(raw_prob.reshape(-1, 1))[:, 1]
