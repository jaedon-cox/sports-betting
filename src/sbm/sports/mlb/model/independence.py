"""Home/away run-distribution independence test (model doc §10.6).

Independence must be TESTED, not assumed: residual correlation after conditioning on
all pre-game features (i.e. after removing each side's own predicted NB mean/variance
structure) is checked against settled games. If material, `nb.py`'s Gaussian-copula
path is used instead of independent draws.

What this needs to actually RUN: a chronological slice of settled games, each with
realized (home_runs, away_runs) and the (mu, alpha) that `mean.py`/`alpha.py`
predicted for that game *at pick time* — i.e. real games have to be simulated and
settled first. That data doesn't exist yet in this build. `assess_residual_independence`
is ready the moment `db`/`ingest` can supply it; `INSUFFICIENT_DATA` is the honest
default until then (see `vertical.py`'s `FITTED_COPULA_RHO = None`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
from scipy import stats

MIN_GAMES_FOR_TEST = 200
"""Below this, a correlation estimate is too noisy to trust (doc's FDR/rigor bar, §10.6)."""

MATERIALITY_THRESHOLD = 0.05
"""|Spearman rho| below this isn't worth the copula's extra variance-model risk."""

SIGNIFICANCE_LEVEL = 0.05


class IndependenceStatus(Enum):
    INDEPENDENT = "independent"
    CORRELATED = "correlated"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class IndependenceTestResult:
    status: IndependenceStatus
    spearman_rho: float | None
    p_value: float | None
    n_games: int
    copula_rho: float | None
    """Gaussian-copula correlation to pass as `NegativeBinomialRunDistribution.rho`
    when `status == CORRELATED`; None otherwise."""


def pearson_residuals(observed_runs: np.ndarray, mu: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Standardized residuals under each game's own fitted NB(mu, alpha).

    Conditions out everything the mean/dispersion model already explains, so what's
    left isolates *residual* home/away dependence (doc §10.6) rather than dependence
    induced by, e.g., both teams sharing the same park/weather that mu already saw.
    """
    variance = mu + alpha * mu**2
    return (observed_runs - mu) / np.sqrt(variance)


def assess_residual_independence(
    home_runs: np.ndarray,
    away_runs: np.ndarray,
    mu_home: np.ndarray,
    mu_away: np.ndarray,
    alpha_home: np.ndarray,
    alpha_away: np.ndarray,
) -> IndependenceTestResult:
    """Spearman test on standardized residuals; Gaussian-copula rho on failure.

    Spearman (not Pearson) because it only needs the residuals' rank relationship,
    not the NB marginals' exact shape. The Gaussian-copula correlation is recovered
    from Spearman's rho via the standard relation rho_normal = 2*sin(pi/6 *
    rho_spearman) (Greiner's formula for a Gaussian copula).
    """
    n = len(home_runs)
    if n < MIN_GAMES_FOR_TEST:
        return IndependenceTestResult(IndependenceStatus.INSUFFICIENT_DATA, None, None, n, None)

    r_home = pearson_residuals(np.asarray(home_runs, dtype=np.float64), mu_home, alpha_home)
    r_away = pearson_residuals(np.asarray(away_runs, dtype=np.float64), mu_away, alpha_away)
    rho, p_value = stats.spearmanr(r_home, r_away)

    if p_value < SIGNIFICANCE_LEVEL and abs(rho) > MATERIALITY_THRESHOLD:
        copula_rho = float(2.0 * np.sin(np.pi / 6.0 * rho))
        return IndependenceTestResult(
            IndependenceStatus.CORRELATED, float(rho), float(p_value), n, copula_rho
        )

    return IndependenceTestResult(IndependenceStatus.INDEPENDENT, float(rho), float(p_value), n, None)
