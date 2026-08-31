"""Moneyline: P(team wins), from the joint (home, away) draws.

An exact tie (home == away) is excluded from both sides via strict `>` —
baseball has no ties, but the market stays push-aware for generality (e.g. a
future sport with draws). `line` is accepted for protocol conformance but
unused.
"""

from __future__ import annotations

import numpy as np

from sbm.contracts.distribution import Draws
from sbm.markets._validate import validate_call


class MoneylineMarket:
    key = "moneyline"
    required_dims = 2
    sides = ("home", "away")

    def probability(self, draws: Draws, side: str, line: float | None) -> float:
        validate_call(draws, side, self.sides, self.required_dims)
        home, away = draws[:, 0], draws[:, 1]
        if side == "home":
            return float(np.mean(home > away))
        return float(np.mean(away > home))
