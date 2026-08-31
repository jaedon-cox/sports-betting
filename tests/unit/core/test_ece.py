"""ece.py: reliability buckets and Expected Calibration Error.

ECE is the second gate metric, so the properties asserted are the ones a
dashboard reader relies on: perfectly calibrated is exactly 0, the number never
leaves [0, 1], and empty buckets are absent rather than zero-filled.
"""

from __future__ import annotations

import numpy as np
import pytest

from sbm.core.calibration import expected_calibration_error, reliability_buckets


def test_perfect_calibration_is_zero() -> None:
    """Every bucket's empirical rate equals its average prediction: half the
    coin-flips win, one in twenty of the 5% shots wins. No gap, no error."""
    prob = np.array([0.5] * 4 + [0.05] * 20)
    outcome = np.array([1.0, 1.0, 0.0, 0.0] + [1.0] + [0.0] * 19)
    assert expected_calibration_error(prob, outcome) == pytest.approx(0.0)


def test_maximally_wrong_calibration_is_one() -> None:
    prob = np.array([0.0, 0.0, 0.0])
    outcome = np.array([1.0, 1.0, 1.0])
    assert expected_calibration_error(prob, outcome) == pytest.approx(1.0)


@pytest.mark.parametrize("seed", range(5))
def test_ece_stays_in_the_unit_interval(seed: int) -> None:
    rng = np.random.default_rng(seed)
    prob = rng.uniform(size=500)
    outcome = (rng.uniform(size=500) < prob).astype(float)
    assert 0.0 <= expected_calibration_error(prob, outcome) <= 1.0


def test_ece_is_the_weighted_mean_gap() -> None:
    """Buckets are weighted by their share of rows, so a big bucket's gap
    dominates a small one's."""
    prob = np.array([0.05] * 90 + [0.95] * 10)
    outcome = np.array([0.0] * 90 + [0.0] * 10)
    assert expected_calibration_error(prob, outcome) == pytest.approx(0.9 * 0.05 + 0.1 * 0.95)


def test_buckets_omit_empty_bins() -> None:
    """Backend doc §3.3 upserts observed rows, not a dense 10-row grid."""
    buckets = reliability_buckets(np.array([0.05, 0.15]), np.array([1.0, 0.0]))
    assert [b.predicted_bucket for b in buckets] == [0, 1]


def test_bucket_edges_and_contents() -> None:
    prob = np.array([0.02, 0.08, 0.55])
    buckets = {b.predicted_bucket: b for b in reliability_buckets(prob, np.array([1.0, 0.0, 1.0]))}
    assert buckets[0].n == 2
    assert (buckets[0].bucket_lo, buckets[0].bucket_hi) == (0.0, 0.1)
    assert buckets[0].avg_predicted_prob == pytest.approx(0.05)
    assert buckets[0].empirical_rate == pytest.approx(0.5)
    assert buckets[5].n == 1


def test_probability_of_one_lands_in_the_top_bucket() -> None:
    """np.digitize would otherwise push p == 1.0 past the last edge."""
    buckets = reliability_buckets(np.array([1.0]), np.array([1.0]))
    assert [b.predicted_bucket for b in buckets] == [9]


def test_bucket_count_is_configurable() -> None:
    prob = np.linspace(0.01, 0.99, 100)
    outcome = (prob > 0.5).astype(float)
    assert len(reliability_buckets(prob, outcome, n_buckets=4)) == 4


def test_length_mismatch_and_empty_input_rejected() -> None:
    with pytest.raises(ValueError):
        reliability_buckets(np.array([0.5]), np.array([1.0, 0.0]))
    with pytest.raises(ValueError):
        expected_calibration_error(np.array([]), np.array([]))
