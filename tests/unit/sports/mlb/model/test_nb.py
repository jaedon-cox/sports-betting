"""nb.py: Distribution-protocol conformance and NB moment sanity."""

from __future__ import annotations

import numpy as np
import pytest

from sbm.contracts.distribution import Distribution
from sbm.sports.mlb.model.nb import NBParams, NegativeBinomialRunDistribution


def _dist(rho: float | None = None) -> NegativeBinomialRunDistribution:
    return NegativeBinomialRunDistribution(
        home=NBParams(mu=4.5, alpha=1.2), away=NBParams(mu=4.0, alpha=1.0), rho=rho
    )


def test_satisfies_distribution_protocol() -> None:
    dist = _dist()
    assert isinstance(dist, Distribution)
    assert dist.n_dims == 2


def test_nbparams_rejects_nonpositive() -> None:
    with pytest.raises(ValueError):
        NBParams(mu=0.0, alpha=1.0)
    with pytest.raises(ValueError):
        NBParams(mu=4.0, alpha=0.0)


def test_sample_shape_and_dtype() -> None:
    draws = _dist().sample(1000, np.random.default_rng(0))
    assert draws.shape == (1000, 2)
    assert draws.dtype == np.float64


def test_sample_is_integer_valued_and_nonnegative() -> None:
    draws = _dist().sample(1000, np.random.default_rng(0))
    assert np.all(draws >= 0)
    assert np.all(draws == np.round(draws))


def test_sample_is_deterministic_under_fixed_seed() -> None:
    dist = _dist()
    a = dist.sample(500, np.random.default_rng(42))
    b = dist.sample(500, np.random.default_rng(42))
    np.testing.assert_array_equal(a, b)


def test_sample_moments_match_nb_theory() -> None:
    params = NBParams(mu=4.5, alpha=1.2)
    dist = NegativeBinomialRunDistribution(home=params, away=params)
    draws = dist.sample(200_000, np.random.default_rng(1))
    home_runs = draws[:, 0]
    expected_var = params.mu + params.alpha * params.mu**2
    assert home_runs.mean() == pytest.approx(params.mu, rel=0.03)
    assert home_runs.var() == pytest.approx(expected_var, rel=0.05)


def test_overdispersed_relative_to_poisson() -> None:
    """Var > mean is the whole point of NB over Poisson (A2)."""
    params = NBParams(mu=4.5, alpha=1.2)
    dist = NegativeBinomialRunDistribution(home=params, away=params)
    draws = dist.sample(200_000, np.random.default_rng(2))
    assert draws[:, 0].var() > draws[:, 0].mean()


def test_copula_path_induces_positive_correlation() -> None:
    dist = _dist(rho=0.5)
    draws = dist.sample(100_000, np.random.default_rng(3))
    corr = np.corrcoef(draws[:, 0], draws[:, 1])[0, 1]
    assert corr > 0.1


def test_independent_path_has_near_zero_correlation() -> None:
    dist = _dist(rho=None)
    draws = dist.sample(100_000, np.random.default_rng(4))
    corr = np.corrcoef(draws[:, 0], draws[:, 1])[0, 1]
    assert abs(corr) < 0.03
