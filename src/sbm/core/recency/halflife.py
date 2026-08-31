"""Half-life -> EWMA decay-factor conversion (model doc §10.1)."""

from __future__ import annotations

HALF_LIVES_GAMES: dict[str, tuple[float, float]] = {
    "bullpen_fatigue": (5.0, 7.0),
    "bullpen_skill": (10.0, 14.0),
    "team_offense": (15.0, 20.0),
    "starters": (20.0, 30.0),
}
"""(min, max) half-life in games per signal family, model doc §10.1. A range,
not a single value — callers (sport verticals) pick a specific point in-range
(e.g. the midpoint) and own that choice; the range itself isn't a model
input."""


def decay_factor(half_life_games: float) -> float:
    """`lambda` such that a weight halves every `half_life_games` steps.

    `weight_t = lambda ** age_in_games`. Solved from `lambda ** h = 0.5`.
    """
    if half_life_games <= 0:
        raise ValueError(f"half_life_games must be > 0, got {half_life_games}")
    return 0.5 ** (1.0 / half_life_games)
