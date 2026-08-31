"""The single abstraction every model output must satisfy.

One distribution shape serves both team markets and player props, which is what
keeps `markets/` sport-agnostic:

    n_dims == 2  ->  game-level joint draws, columns (home, away)
    n_dims == 1  ->  player-level draws, one column of stat values

Markets consume *drawn samples*, never the distribution itself (see market.py),
so a single Monte-Carlo draw feeds moneyline, total and run-line at once — the
"one unified run-distribution model serves all three markets" decision
(model doc A2/A3).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from numpy.random import Generator
from numpy.typing import NDArray

Draws = NDArray[np.float64]
"""Monte-Carlo samples, shape (n, n_dims). Integer-valued for count outcomes."""


@runtime_checkable
class Distribution(Protocol):
    """A sampleable predictive distribution for one game or one player-stat."""

    n_dims: int
    """2 for joint game outcomes (home, away); 1 for a univariate prop stat."""

    def sample(self, n: int, rng: Generator) -> Draws:
        """Draw `n` samples, returning shape (n, self.n_dims).

        Must be pure: same `rng` state and `n` yield identical draws. Analytical
        shortcuts for sums are forbidden — the sum of two Negative-Binomials is
        not NB in general (model doc A3).
        """
        ...
