"""independence.py: insufficient-data default, and detection on synthetic residuals."""

from __future__ import annotations

import numpy as np

from sbm.sports.mlb.model.independence import (
    MIN_GAMES_FOR_TEST,
    IndependenceStatus,
    assess_residual_independence,
)


def _synthetic_games(n: int, rho: float, rng: np.random.Generator) -> tuple[np.ndarray, ...]:
    mu_home = np.full(n, 4.5)
    mu_away = np.full(n, 4.0)
    alpha_home = np.full(n, 1.2)
    alpha_away = np.full(n, 1.0)
    cov = np.array([[1.0, rho], [rho, 1.0]])
    z = rng.multivariate_normal([0.0, 0.0], cov, size=n)
    # Map correlated normals straight to run counts via a simple positive
    # transform — enough to induce a detectable rank correlation in residuals
    # without needing a full copula round-trip for this unit test.
    home_runs = np.clip(np.round(mu_home + z[:, 0] * np.sqrt(mu_home + alpha_home * mu_home**2)), 0, None)
    away_runs = np.clip(np.round(mu_away + z[:, 1] * np.sqrt(mu_away + alpha_away * mu_away**2)), 0, None)
    return home_runs, away_runs, mu_home, mu_away, alpha_home, alpha_away


def test_insufficient_data_below_minimum() -> None:
    n = MIN_GAMES_FOR_TEST - 1
    args = _synthetic_games(n, rho=0.0, rng=np.random.default_rng(0))
    result = assess_residual_independence(*args)
    assert result.status == IndependenceStatus.INSUFFICIENT_DATA
    assert result.copula_rho is None
    assert result.n_games == n


def test_detects_independence_when_uncorrelated() -> None:
    args = _synthetic_games(5000, rho=0.0, rng=np.random.default_rng(1))
    result = assess_residual_independence(*args)
    assert result.status == IndependenceStatus.INDEPENDENT
    assert result.copula_rho is None


def test_detects_correlation_when_material() -> None:
    args = _synthetic_games(5000, rho=0.5, rng=np.random.default_rng(2))
    result = assess_residual_independence(*args)
    assert result.status == IndependenceStatus.CORRELATED
    assert result.copula_rho is not None
    assert result.copula_rho > 0
