"""Negative-Binomial run-distribution — the `Distribution` every MLB market draws from.

MLB team run-scoring is over-dispersed (variance > mean); Poisson assumes variance ==
mean and is not an acceptable fallback here (model doc A2). Two independent per-side NB
marginals are joined via an optional Gaussian-copula correlation (see `independence.py`)
rather than assumed independent outright — independence is tested, not asserted (§10.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np
from numpy.random import Generator
from scipy import stats

from sbm.contracts.distribution import Draws


@dataclass(frozen=True, slots=True)
class NBParams:
    """Per-side NB parameters for one game: mean runs and over-dispersion.

    `alpha` is the NB2 dispersion parameter: Var = mu + alpha * mu**2. alpha -> 0
    recovers Poisson; MLB run scoring needs alpha > 0 (A2) and it must vary by
    matchup, never be a fixed constant (A6) — see `alpha.py`.
    """

    mu: float
    alpha: float

    def __post_init__(self) -> None:
        if self.mu <= 0:
            raise ValueError(f"mu must be positive, got {self.mu}")
        if self.alpha <= 0:
            raise ValueError(f"alpha must be positive, got {self.alpha}")

    @property
    def size(self) -> float:
        """NB `n` (number-of-successes) parameter. n = 1/alpha — independent of mu
        under the NB2 mean/dispersion parameterization used throughout this package."""
        return 1.0 / self.alpha

    @property
    def prob(self) -> float:
        """NB `p` (success-probability) parameter, derived from mu and alpha."""
        return 1.0 / (1.0 + self.alpha * self.mu)


@dataclass(frozen=True, slots=True)
class NegativeBinomialRunDistribution:
    """Joint (home, away) run distribution for one game.

    Satisfies `contracts.distribution.Distribution`: n_dims=2, columns (home, away).
    `rho` is the fitted Gaussian-copula correlation from `independence.py`'s test;
    None (the default) draws the two sides independently.
    """

    home: NBParams
    away: NBParams
    rho: float | None = None
    n_dims: ClassVar[int] = 2

    def sample(self, n: int, rng: Generator) -> Draws:
        """Draw `n` (home, away) run pairs. Pure given `rng`'s state (contract's
        determinism requirement) — no analytical convolution shortcut is taken
        anywhere in this package (A3); callers needing a sum/margin do it on these
        drawn samples, not on a derived closed-form distribution.
        """
        if self.rho is None or self.rho == 0.0:
            home_runs = rng.negative_binomial(self.home.size, self.home.prob, size=n)
            away_runs = rng.negative_binomial(self.away.size, self.away.prob, size=n)
        else:
            home_runs, away_runs = _sample_via_gaussian_copula(self.home, self.away, self.rho, n, rng)
        return np.column_stack([home_runs, away_runs]).astype(np.float64)


def _sample_via_gaussian_copula(
    home: NBParams, away: NBParams, rho: float, n: int, rng: Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Correlated NB draws via a standard-normal copula -> per-side NB quantiles.

    Used only when `independence.py` finds material residual correlation between
    home and away runs (model doc §10.6). `rho` is the copula's Pearson correlation
    on the normal scale, already converted from the test's Spearman estimate.
    """
    cov = np.array([[1.0, rho], [rho, 1.0]])
    z = rng.multivariate_normal(mean=[0.0, 0.0], cov=cov, size=n)
    u = stats.norm.cdf(z)
    home_runs = stats.nbinom.ppf(u[:, 0], home.size, home.prob)
    away_runs = stats.nbinom.ppf(u[:, 1], away.size, away.prob)
    return home_runs, away_runs
