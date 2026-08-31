"""GBT ensemble/regularization component (model doc A4) — NOT the primary model.

Bradley-Terry was rejected as primary because it discards the run distribution
entirely; GBT is allowed only as an ensemble add-on, and only if it clears a
pre-specified Brier-score threshold against a regularization grid FIXED before
testing (§10.6: "no post-hoc justification"). This module defines that gate.

No held-out settled-game data exists yet to run `evaluate_gate` for real, so every
caller today gets pure NB probabilities via `blend` — the ensemble ships inert by
design until a gate result with `passed=True` exists, never silently ungated.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

BRIER_IMPROVEMENT_THRESHOLD = 0.002
"""GBT must beat the NB-only Brier score by at least this much on the held-out
chronological slice (A5) to be trusted — fixed before any GBT is fit (§10.6)."""

REGULARIZATION_GRID: tuple[dict[str, float | int], ...] = (
    {"n_estimators": 100, "max_depth": 2, "learning_rate": 0.05, "subsample": 0.8},
    {"n_estimators": 200, "max_depth": 2, "learning_rate": 0.03, "subsample": 0.8},
    {"n_estimators": 100, "max_depth": 3, "learning_rate": 0.05, "subsample": 0.6},
)
"""Fixed BEFORE any Brier-score comparison is run (doc §10.6) — editing this after
seeing held-out results defeats the point of a pre-specified grid."""


@dataclass(frozen=True, slots=True)
class GBTGateResult:
    passed: bool
    nb_brier: float
    best_gbt_brier: float | None
    best_params: dict[str, float | int] | None


def brier_score(y_true: np.ndarray, p_pred: np.ndarray) -> float:
    return float(np.mean((np.asarray(p_pred) - np.asarray(y_true)) ** 2))


def evaluate_gate(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_holdout: np.ndarray,
    y_holdout: np.ndarray,
    nb_only_prob_holdout: np.ndarray,
) -> GBTGateResult:
    """Fit each grid config on TRAIN, score on the chronological HOLDOUT (A5).

    `nb_only_prob_holdout` is the NB model's own probability for the same holdout
    games — the baseline the GBT ensemble must beat by
    `BRIER_IMPROVEMENT_THRESHOLD` to be allowed into production (A4).
    """
    nb_brier = brier_score(y_holdout, nb_only_prob_holdout)
    best_brier: float | None = None
    best_params: dict[str, float | int] | None = None

    for params in REGULARIZATION_GRID:
        model = GradientBoostingClassifier(**params)
        model.fit(x_train, y_train)
        p = model.predict_proba(x_holdout)[:, 1]
        b = brier_score(y_holdout, p)
        if best_brier is None or b < best_brier:
            best_brier, best_params = b, params

    passed = best_brier is not None and (nb_brier - best_brier) >= BRIER_IMPROVEMENT_THRESHOLD
    return GBTGateResult(passed=passed, nb_brier=nb_brier, best_gbt_brier=best_brier, best_params=best_params)


def blend(nb_prob: np.ndarray, gbt_prob: np.ndarray | None, gate: GBTGateResult | None) -> np.ndarray:
    """NB-only unless the gate has actually passed — inert by default.

    No held-out data exists yet to run `evaluate_gate` for real, so every caller
    today gets pure NB probabilities back unchanged. This is the seam where a
    future, gate-passing GBT plugs in without any caller needing to change.
    """
    if gate is None or not gate.passed or gbt_prob is None:
        return np.asarray(nb_prob, dtype=np.float64)
    return 0.5 * np.asarray(nb_prob, dtype=np.float64) + 0.5 * np.asarray(gbt_prob, dtype=np.float64)
