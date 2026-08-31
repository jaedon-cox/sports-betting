"""splits.py: the chronological 3-way split A5 depends on.

The one property that matters is ordering: every calibration row is later than
every training row, and every test row later than both. A split that leaked in
either direction would make the calibrated probability — and therefore CLV —
fictitious.
"""

from __future__ import annotations

import numpy as np
import pytest

from sbm.core.calibration import chronological_split


def _timestamps(n: int = 100) -> np.ndarray:
    return np.arange(n, dtype=np.float64)


def test_slices_partition_every_row_exactly_once() -> None:
    split = chronological_split(_timestamps())
    stacked = np.vstack([split.train, split.calibration, split.test])
    assert np.all(stacked.sum(axis=0) == 1)


def test_ordering_is_train_then_calibration_then_test() -> None:
    ts = _timestamps()
    split = chronological_split(ts)
    assert ts[split.train].max() < ts[split.calibration].min()
    assert ts[split.calibration].max() < ts[split.test].min()


def test_fractions_are_of_row_count() -> None:
    split = chronological_split(_timestamps(100), train_frac=0.6, calibration_frac=0.2)
    assert (split.train.sum(), split.calibration.sum(), split.test.sum()) == (60, 20, 20)


def test_unsorted_input_still_splits_chronologically() -> None:
    """Callers pass rows in original order; the split sorts internally and
    returns masks aligned to that order (docstring)."""
    rng = np.random.default_rng(0)
    ts = rng.permutation(_timestamps())
    split = chronological_split(ts)
    assert ts[split.train].max() < ts[split.calibration].min()
    assert ts[split.calibration].max() < ts[split.test].min()


def test_masks_align_to_the_input_row_order() -> None:
    ts = np.array([5.0, 1.0, 3.0])
    split = chronological_split(ts, train_frac=0.34, calibration_frac=0.34)
    assert split.train[1] and split.calibration[2] and split.test[0]


def test_datetime_like_timestamps_are_accepted() -> None:
    from datetime import UTC, datetime, timedelta

    base = datetime(2024, 4, 1, tzinfo=UTC)
    ts = [base + timedelta(days=i) for i in range(50)]
    split = chronological_split(ts)
    assert split.train[:30].all() and split.test[-10:].all()


@pytest.mark.parametrize(
    ("train_frac", "calibration_frac"),
    [(0.0, 0.2), (1.0, 0.2), (0.6, 0.0), (0.6, 1.0), (0.8, 0.2), (0.9, 0.2)],
)
def test_degenerate_fractions_rejected(train_frac: float, calibration_frac: float) -> None:
    """A split with no test slice would report in-sample numbers as out-of-sample."""
    with pytest.raises(ValueError):
        chronological_split(_timestamps(), train_frac=train_frac, calibration_frac=calibration_frac)
