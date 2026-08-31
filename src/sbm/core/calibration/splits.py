"""Chronological train / calibration / test split (model doc A5).

Calibration must fit on a *later* held-out slice, never training data — a
temporal split, not a random one. Order along the split is
train (earliest) -> calibration (middle) -> test (latest, held out).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class ChronoSplit:
    """Boolean row masks (aligned to the original row order) for a 3-way split."""

    train: NDArray[np.bool_]
    calibration: NDArray[np.bool_]
    test: NDArray[np.bool_]


def chronological_split(
    timestamps: Sequence,
    *,
    train_frac: float = 0.6,
    calibration_frac: float = 0.2,
) -> ChronoSplit:
    """Split rows into 3 chronological slices by row count, not calendar time.

    `timestamps` need not be pre-sorted — the split is computed via
    `np.argsort`, so callers pass any orderable sequence (dates, datetimes,
    ints) in original row order and get back masks aligned to that order.
    Fractions are of row count (not calendar time) since MLB slate size
    varies seasonally; the remainder after `train_frac + calibration_frac`
    becomes the test slice.
    """
    if not 0.0 < train_frac < 1.0:
        raise ValueError(f"train_frac must be in (0, 1), got {train_frac}")
    if not 0.0 < calibration_frac < 1.0:
        raise ValueError(f"calibration_frac must be in (0, 1), got {calibration_frac}")
    if train_frac + calibration_frac >= 1.0:
        raise ValueError("train_frac + calibration_frac must leave room for a test slice")

    n = len(timestamps)
    order = np.argsort(np.asarray(timestamps))
    n_train = int(n * train_frac)
    n_cal = int(n * calibration_frac)

    train = np.zeros(n, dtype=bool)
    calibration = np.zeros(n, dtype=bool)
    test = np.zeros(n, dtype=bool)

    train[order[:n_train]] = True
    calibration[order[n_train : n_train + n_cal]] = True
    test[order[n_train + n_cal :]] = True

    return ChronoSplit(train=train, calibration=calibration, test=test)
