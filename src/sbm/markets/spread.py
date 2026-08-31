"""Spread: P(side covers), from the joint (home, away) draws.

Run-line (MLB) is a spread with `line = +-1.5` (CLAUDE.md) — no separate
market file.

`line` is always expressed from the HOME team's perspective (e.g. -1.5 when
home is favored by 1.5), regardless of which `side` is queried — this mirrors
`total.py`'s single shared line rather than requiring a second, sign-flipped
line for the away side. Home covers when `margin_home > -line`; away covers
exactly when home does not, i.e. `margin_home < -line`. An exact push
(`margin_home == -line`) is excluded from both, as usual.
"""

from __future__ import annotations

import numpy as np

from sbm.contracts.distribution import Draws
from sbm.markets._validate import validate_call


class SpreadMarket:
    key = "spread"
    required_dims = 2
    sides = ("home", "away")

    def probability(self, draws: Draws, side: str, line: float | None) -> float:
        validate_call(draws, side, self.sides, self.required_dims)
        if line is None:
            raise ValueError("spread market requires a line")
        margin_home = draws[:, 0] - draws[:, 1]
        if side == "home":
            return float(np.mean(margin_home > -line))
        return float(np.mean(margin_home < -line))
