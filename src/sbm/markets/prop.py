"""Player prop: P(stat over/under `line`), from a 1-column draw distribution.

Structurally identical to `total.py` but bound to `required_dims = 1` — this
is the proof the `Market`/`Distribution` abstraction generalizes to
player-level props, even though no sport vertical produces a 1-dim
distribution yet (CLAUDE.md).
"""

from __future__ import annotations

import numpy as np

from sbm.contracts.distribution import Draws
from sbm.markets._validate import validate_call


class PropMarket:
    key = "prop"
    required_dims = 1
    sides = ("over", "under")

    def probability(self, draws: Draws, side: str, line: float | None) -> float:
        validate_call(draws, side, self.sides, self.required_dims)
        if line is None:
            raise ValueError("prop market requires a line")
        stat = draws[:, 0]
        if side == "over":
            return float(np.mean(stat > line))
        return float(np.mean(stat < line))
