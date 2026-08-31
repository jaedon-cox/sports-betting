"""Monte Carlo convolution — the ONLY way home/away NB draws become game-level
joint/margin/total outcomes (model doc A3).

The sum of two Negative-Binomials is not NB in general, so there is no analytical
shortcut for totals or run-line: every market-facing number comes from drawn samples.
Vectorized per game so a ~15-game slate runs in well under a minute at N=100k
draws/game/side (backend doc §2.2) — see `tests/unit/sports/mlb/model/test_simulate.py`
for the timing check.
"""

from __future__ import annotations

import numpy as np
from numpy.random import Generator

from sbm.contracts.distribution import Draws
from sbm.sports.mlb.model.nb import NegativeBinomialRunDistribution

DEFAULT_N_DRAWS = 100_000
"""Draws/game/side — backend doc §2.2's target for a daily slate run."""


def simulate_game(
    dist: NegativeBinomialRunDistribution, rng: Generator, n: int = DEFAULT_N_DRAWS
) -> Draws:
    """One game's (home, away) draws.

    Thin wrapper — the real work (and the "no analytical shortcut" rule) lives in
    `Distribution.sample`; this exists so slate-level code has one call site to
    change if a market ever needs a non-default `n`.
    """
    return dist.sample(n, rng)


def simulate_slate(
    distributions: dict[str, NegativeBinomialRunDistribution],
    rng: Generator,
    n: int = DEFAULT_N_DRAWS,
) -> dict[str, Draws]:
    """Simulate every game in a slate, one `Draws` array per `game_id`.

    Each game draws from the SAME `rng` stream, advanced in dict-iteration order, so
    a fixed seed reproduces the whole slate deterministically (contracts/distribution
    .py's determinism requirement). Callers that need one game's draws to be
    independent of every other game's position in the dict (e.g. parallel execution,
    or re-running a single game without perturbing the rest) should use
    `spawn_child_generators` instead and pass each game its own child `Generator`.
    """
    return {game_id: dist.sample(n, rng) for game_id, dist in distributions.items()}


def spawn_child_generators(rng: Generator, n_children: int) -> list[Generator]:
    """Independent, reproducible child RNG streams — one per game.

    Lets a slate simulate out of order (or in parallel) without one game's draw
    count perturbing another's stream, while staying fully reproducible under a
    fixed parent seed. `Generator.spawn` (NumPy >=1.25) derives non-overlapping
    streams from the parent's bit generator.
    """
    return list(rng.spawn(n_children))


def slate_margins(draws_by_game: dict[str, Draws]) -> dict[str, np.ndarray]:
    """home - away run margin per drawn sample, per game — the run-line's raw input.

    Still a post-hoc reduction on already-drawn samples, not a shortcut around the
    convolution itself (A3): the draws in `draws_by_game` were produced by
    `simulate_slate`/`simulate_game`, never by an analytical sum.
    """
    return {game_id: draws[:, 0] - draws[:, 1] for game_id, draws in draws_by_game.items()}
