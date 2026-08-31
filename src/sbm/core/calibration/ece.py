"""Expected Calibration Error + reliability-diagram buckets.

Bucket layout follows the DB's `calibration_buckets` design (backend doc
§3.3): 10 equal-width deciles via `width_bucket()`-equivalent binning. The
frontend renders `reliability_buckets` output directly as the reliability
chart.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class ReliabilityBucket:
    """One bucket of a reliability diagram."""

    predicted_bucket: int
    """Decile index 0-9, matching `calibration_buckets.predicted_bucket`."""
    bucket_lo: float
    bucket_hi: float
    n: int
    avg_predicted_prob: float
    empirical_rate: float


def reliability_buckets(
    predicted_prob: NDArray[np.float64],
    outcome: NDArray[np.float64],
    *,
    n_buckets: int = 10,
) -> list[ReliabilityBucket]:
    """Bucket predictions into `n_buckets` equal-width bins on [0, 1].

    Empty buckets are omitted — a row with no observations isn't meaningful
    (backend doc §3.3 persists this via `INSERT/UPSERT`, not a dense grid).
    """
    if len(predicted_prob) != len(outcome):
        raise ValueError("predicted_prob and outcome must be the same length")
    edges = np.linspace(0.0, 1.0, n_buckets + 1)
    idx = np.clip(np.digitize(predicted_prob, edges[1:-1], right=False), 0, n_buckets - 1)

    buckets = []
    for b in range(n_buckets):
        mask = idx == b
        n = int(mask.sum())
        if n == 0:
            continue
        buckets.append(
            ReliabilityBucket(
                predicted_bucket=b,
                bucket_lo=float(edges[b]),
                bucket_hi=float(edges[b + 1]),
                n=n,
                avg_predicted_prob=float(predicted_prob[mask].mean()),
                empirical_rate=float(outcome[mask].mean()),
            )
        )
    return buckets


def expected_calibration_error(
    predicted_prob: NDArray[np.float64],
    outcome: NDArray[np.float64],
    *,
    n_buckets: int = 10,
) -> float:
    """ECE = sum over buckets of `(n_bucket / n_total) * |avg_pred - empirical_rate|`."""
    n_total = len(predicted_prob)
    if n_total == 0:
        raise ValueError("cannot compute ECE on empty input")
    buckets = reliability_buckets(predicted_prob, outcome, n_buckets=n_buckets)
    return sum((b.n / n_total) * abs(b.avg_predicted_prob - b.empirical_rate) for b in buckets)
