"""gbt.py: the ensemble stays inert until a gate result explicitly passes."""

from __future__ import annotations

import numpy as np

from sbm.sports.mlb.model.gbt import GBTGateResult, blend, brier_score, evaluate_gate


def test_blend_is_pure_nb_when_gate_is_none() -> None:
    nb_prob = np.array([0.5, 0.6, 0.4])
    out = blend(nb_prob, gbt_prob=np.array([0.9, 0.9, 0.9]), gate=None)
    np.testing.assert_array_equal(out, nb_prob)


def test_blend_is_pure_nb_when_gate_fails() -> None:
    nb_prob = np.array([0.5, 0.6, 0.4])
    gate = GBTGateResult(passed=False, nb_brier=0.2, best_gbt_brier=0.19, best_params=None)
    out = blend(nb_prob, gbt_prob=np.array([0.9, 0.9, 0.9]), gate=gate)
    np.testing.assert_array_equal(out, nb_prob)


def test_blend_uses_gbt_when_gate_passes() -> None:
    nb_prob = np.array([0.5])
    gbt_prob = np.array([0.9])
    gate = GBTGateResult(passed=True, nb_brier=0.2, best_gbt_brier=0.1, best_params={})
    out = blend(nb_prob, gbt_prob=gbt_prob, gate=gate)
    assert out[0] == 0.7


def test_brier_score_perfect_prediction_is_zero() -> None:
    assert brier_score(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == 0.0


def test_evaluate_gate_runs_grid_and_reports_baseline() -> None:
    rng = np.random.default_rng(0)
    x_train = rng.normal(size=(200, 4))
    y_train = (x_train[:, 0] + rng.normal(scale=0.5, size=200) > 0).astype(float)
    x_holdout = rng.normal(size=(100, 4))
    y_holdout = (x_holdout[:, 0] + rng.normal(scale=0.5, size=100) > 0).astype(float)
    nb_only_prob = np.full(100, 0.5)  # deliberately uninformative baseline

    result = evaluate_gate(x_train, y_train, x_holdout, y_holdout, nb_only_prob)

    assert result.nb_brier == brier_score(y_holdout, nb_only_prob)
    assert result.best_gbt_brier is not None
    assert isinstance(result.passed, bool)
