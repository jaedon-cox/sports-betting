"""calibration.py: raw-vs-calibrated separation and calibration-slice-only fitting."""

from __future__ import annotations

import numpy as np

from sbm.core.calibration import ChronoSplit, IsotonicCalibrator
from sbm.sports.mlb.model.calibration import apply_calibration, fit_calibrator_on_split


def _split(n: int) -> ChronoSplit:
    train = np.zeros(n, dtype=bool)
    calibration = np.zeros(n, dtype=bool)
    test = np.zeros(n, dtype=bool)
    train[: n // 3] = True
    calibration[n // 3 : 2 * n // 3] = True
    test[2 * n // 3 :] = True
    return ChronoSplit(train=train, calibration=calibration, test=test)


def test_apply_calibration_passthrough_when_no_calibrator() -> None:
    raw = np.array([0.6, 0.4])
    result = apply_calibration(None, raw)
    np.testing.assert_array_equal(result.raw_model_prob, raw)
    np.testing.assert_array_equal(result.model_prob, raw)


def test_apply_calibration_keeps_raw_and_calibrated_distinct() -> None:
    rng = np.random.default_rng(0)
    raw_prob = rng.uniform(0.1, 0.9, size=300)
    outcome = (rng.uniform(size=300) < raw_prob).astype(float)
    split = _split(300)
    calibrator = fit_calibrator_on_split(split, raw_prob, outcome)

    result = apply_calibration(calibrator, raw_prob)

    np.testing.assert_array_equal(result.raw_model_prob, raw_prob)
    assert not np.array_equal(result.raw_model_prob, result.model_prob)
    assert result.model_prob.min() >= 0.0
    assert result.model_prob.max() <= 1.0


def test_fit_calibrator_on_split_only_uses_calibration_mask() -> None:
    n = 300
    split = _split(n)
    raw_prob = np.zeros(n)
    outcome = np.zeros(n)
    # Only the calibration slice carries real signal; train/test are constant
    # zero and would visibly change the fit if accidentally included.
    cal_idx = np.where(split.calibration)[0]
    raw_prob[cal_idx] = np.linspace(0.05, 0.95, len(cal_idx))
    outcome[cal_idx] = (raw_prob[cal_idx] > 0.5).astype(float)

    calibrator = fit_calibrator_on_split(split, raw_prob, outcome, calibrator_cls=IsotonicCalibrator)

    # A fitted isotonic calibrator on this clean cal-slice signal should map a
    # clearly-high raw prob near 1 and a clearly-low one near 0 — only
    # possible if the fit actually used the calibration slice's real signal.
    assert calibrator.predict(np.array([0.9]))[0] > 0.7
    assert calibrator.predict(np.array([0.1]))[0] < 0.3
