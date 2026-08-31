"""simulate.py: slate-level determinism, correctness, and the N=100k/15-game timing bar."""

from __future__ import annotations

import time

import numpy as np

from sbm.sports.mlb.model.nb import NBParams, NegativeBinomialRunDistribution
from sbm.sports.mlb.model.simulate import (
    DEFAULT_N_DRAWS,
    simulate_slate,
    slate_margins,
    spawn_child_generators,
)


def _slate(n_games: int) -> dict[str, NegativeBinomialRunDistribution]:
    return {
        f"game_{i}": NegativeBinomialRunDistribution(
            home=NBParams(mu=4.0 + 0.1 * i, alpha=1.0), away=NBParams(mu=3.8, alpha=0.9)
        )
        for i in range(n_games)
    }


def test_simulate_slate_shapes() -> None:
    slate = _slate(5)
    draws = simulate_slate(slate, np.random.default_rng(0), n=1000)
    assert set(draws) == set(slate)
    for arr in draws.values():
        assert arr.shape == (1000, 2)


def test_simulate_slate_deterministic_under_fixed_seed() -> None:
    slate = _slate(5)
    a = simulate_slate(slate, np.random.default_rng(7), n=1000)
    b = simulate_slate(slate, np.random.default_rng(7), n=1000)
    for game_id in slate:
        np.testing.assert_array_equal(a[game_id], b[game_id])


def test_spawn_child_generators_are_independent_and_reproducible() -> None:
    parent_a = np.random.default_rng(9)
    parent_b = np.random.default_rng(9)
    children_a = spawn_child_generators(parent_a, 3)
    children_b = spawn_child_generators(parent_b, 3)
    for ca, cb in zip(children_a, children_b, strict=True):
        np.testing.assert_array_equal(ca.random(10), cb.random(10))
    draws0 = children_a[0].random(10)
    draws1 = children_a[1].random(10)
    assert not np.array_equal(draws0, draws1)


def test_slate_margins_is_home_minus_away() -> None:
    slate = _slate(2)
    draws = simulate_slate(slate, np.random.default_rng(1), n=100)
    margins = slate_margins(draws)
    for game_id in slate:
        np.testing.assert_array_equal(margins[game_id], draws[game_id][:, 0] - draws[game_id][:, 1])


def test_full_slate_at_production_n_runs_well_under_a_minute() -> None:
    """Backend doc §2.2: a ~15-game slate at N=100k draws/game/side must run in
    well under a minute. Numpy-vectorized NB sampling has no analytical shortcut
    (A3) to fall back on, so this is the real cost of the daily pipeline."""
    slate = _slate(15)
    start = time.perf_counter()
    draws = simulate_slate(slate, np.random.default_rng(42), n=DEFAULT_N_DRAWS)
    elapsed = time.perf_counter() - start
    assert len(draws) == 15
    for arr in draws.values():
        assert arr.shape == (DEFAULT_N_DRAWS, 2)
    assert elapsed < 15.0, f"15-game slate at N={DEFAULT_N_DRAWS} took {elapsed:.2f}s"
