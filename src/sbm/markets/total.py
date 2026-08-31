"""Total: P(home + away over/under `line`).

An exact tie at `line` (e.g. total == line for a non-.5 line) is a push,
excluded from both sides via strict `>`/`<`.
"""

from __future__ import annotations

import numpy as np

from sbm.contracts.distribution import Draws
from sbm.markets._validate import validate_call


class TotalMarket:
    key = "total"
    required_dims = 2
    sides = ("over", "under")

    def probability(self, draws: Draws, side: str, line: float | None) -> float:
        validate_call(draws, side, self.sides, self.required_dims)
        if line is None:
            raise ValueError("total market requires a line")
        total = draws[:, 0] + draws[:, 1]
        if side == "over":
            return float(np.mean(total > line))
        return float(np.mean(total < line))
