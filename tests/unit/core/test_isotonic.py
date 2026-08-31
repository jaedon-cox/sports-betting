"""isotonic.py: the calibrators applied to `raw_model_prob` to get `model_prob`."""

from __future__ import annotations

import numpy as np
import pytest

from sbm.core.calibration import Calibrator, IsotonicCalibrator, PlattCalibrator

CALIBRATORS = (IsotonicCalibrator, PlattCalibrator)


def _overconfident_sample(n: int = 2000, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Raw probs pushed away from 0.5 — the miscalibration shape a Monte-Carlo
    model actually produces, and the one calibration exists to undo."""
    rng = np.random.default_rng(seed)
    true_prob = rng.uniform(0.2, 0.8, size=n)
    raw = np.clip((true_prob - 0.5) * 1.6 + 0.5, 0.01, 0.99)
    outcome = (rng.uniform(size=n) < true_prob).astype(float)
    return raw, outcome


@pytest.mark.parametrize("cls", CALIBRATORS)
def test_satisfies_the_calibrator_protocol(cls: type) -> None:
    raw, outcome = _overconfident_sample()
    assert isinstance(cls.fit(raw, outcome), Calibrator)


@pytest.mark.parametrize("cls", CALIBRATORS)
def test_output_is_monotone_in_the_raw_probability(cls: type) -> None:
    """Calibration may rescale confidence but must never reorder two picks —
    a non-monotone map would make a lower raw prob the better bet."""
    raw, outcome = _overconfident_sample()
    calibrated = cls.fit(raw, outcome).predict(np.linspace(0.05, 0.95, 50))
    assert np.all(np.diff(calibrated) >= -1e-12)


@pytest.mark.parametrize("cls", CALIBRATORS)
def test_output_stays_a_probability(cls: type) -> None:
    raw, outcome = _overconfident_sample()
    calibrated = cls.fit(raw, outcome).predict(np.linspace(0.0, 1.0, 101))
    assert np.all((calibrated >= 0.0) & (calibrated <= 1.0))


@pytest.mark.parametrize("cls", CALIBRATORS)
def test_calibration_reduces_calibration_error(cls: type) -> None:
    """The point of the layer: apply it to a held-out slice and ECE falls."""
    from sbm.core.calibration import expected_calibration_error

    raw, outcome = _overconfident_sample(seed=1)
    holdout_raw, holdout_outcome = _overconfident_sample(seed=2)
    calibrated = cls.fit(raw, outcome).predict(holdout_raw)
    before = expected_calibration_error(holdout_raw, holdout_outcome)
    after = expected_calibration_error(calibrated, holdout_outcome)
    assert after < before


def test_isotonic_clips_outside_the_fitted_range() -> None:
    """`out_of_bounds="clip"`: a live prob past anything seen in the calibration
    slice must still return a probability, not extrapolate or raise."""
    raw = np.linspace(0.3, 0.7, 200)
    outcome = (raw > 0.5).astype(float)
    calibrated = IsotonicCalibrator.fit(raw, outcome).predict(np.array([0.0, 1.0]))
    assert np.all((calibrated >= 0.0) & (calibrated <= 1.0))


def test_platt_is_smooth_where_isotonic_is_a_step() -> None:
    """The reason Platt is the thin-slice fallback: isotonic on a tiny sample
    collapses to a step function, Platt keeps a gradient."""
    raw = np.array([0.2, 0.3, 0.4, 0.6, 0.7, 0.8])
    outcome = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    grid = np.linspace(0.2, 0.8, 25)
    platt = PlattCalibrator.fit(raw, outcome).predict(grid)
    isotonic = IsotonicCalibrator.fit(raw, outcome).predict(grid)
    assert len(np.unique(platt)) > len(np.unique(isotonic))
