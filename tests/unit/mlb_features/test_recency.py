"""`recency_weighted_by_entity` is pure assembly over `core`'s EWMA fold.

The two behaviours worth pinning are the ones this module is *responsible*
for on `core`'s behalf (see its docstring): dropping rows captured after
`as_of`, and handing `core` rows in chronological order. Both are silent
correctness failures if they regress — `core.ewma_rate` decays by row
position, so unordered or future-bearing input returns a wrong number
rather than raising.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from sbm.core.recency import ewma_asof
from sbm.sports.mlb.features.recency import (
    EFFECTIVE_SAMPLE_SIZE,
    RATE,
    recency_weighted_by_entity,
)


def _recording_ewma(seen: dict[str, list[float]]):
    """Stand-in `EwmaFn` that records the events it was handed, in order."""

    def ewma(
        events: np.ndarray, opportunities: np.ndarray, half_life_games: float
    ) -> tuple[float, float]:
        del half_life_games
        seen.setdefault("events", []).extend(events.tolist())
        return float(events.sum()), float(opportunities.sum())

    return ewma


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pitcher_id": [1, 1, 1, 2, 2],
            "pitches": [20.0, 25.0, 30.0, 10.0, 12.0],
            "outs": [9.0, 12.0, 15.0, 3.0, 6.0],
            "captured_at_utc": [datetime(2026, 6, i, tzinfo=UTC) for i in (1, 2, 3, 1, 2)],
        }
    )


def _run(history: pd.DataFrame, as_of: datetime, ewma=ewma_asof) -> pd.DataFrame:
    return recency_weighted_by_entity(
        history,
        entity_col="pitcher_id",
        events_col="pitches",
        opportunities_col="outs",
        captured_at_col="captured_at_utc",
        half_life_games=6.0,
        as_of=as_of,
        ewma=ewma,
    )


def test_collapses_each_entity_independently() -> None:
    seen: dict[str, list[float]] = {}
    result = _run(_history(), datetime(2026, 6, 3, tzinfo=UTC), _recording_ewma(seen))
    assert list(result.index) == [1, 2]
    assert list(result.columns) == [RATE, EFFECTIVE_SAMPLE_SIZE]
    assert result.loc[1, RATE] == 75.0  # 20 + 25 + 30, entity 1 only
    assert result.loc[2, RATE] == 22.0  # 10 + 12, entity 2 only


def test_rows_captured_after_as_of_are_invisible() -> None:
    """CLAUDE.md rule 4 — the leakage guard, re-applied here on purpose."""
    result = _run(_history(), datetime(2026, 6, 1, 12, tzinfo=UTC))
    both = _run(_history(), datetime(2026, 6, 3, tzinfo=UTC))
    assert result.loc[1, EFFECTIVE_SAMPLE_SIZE] < both.loc[1, EFFECTIVE_SAMPLE_SIZE]


def test_history_entirely_after_as_of_returns_empty() -> None:
    result = _run(_history(), datetime(2026, 5, 1, tzinfo=UTC))
    assert result.empty
    assert list(result.columns) == [RATE, EFFECTIVE_SAMPLE_SIZE]


def test_core_receives_rows_in_chronological_order() -> None:
    """`core.ewma_rate` decays by row position — shuffled input is a wrong
    number, not an error, so ordering is this module's job to guarantee."""
    shuffled = _history().iloc[[2, 0, 1, 4, 3]]
    seen: dict[str, list[float]] = {}
    _run(shuffled, datetime(2026, 6, 3, tzinfo=UTC), _recording_ewma(seen))
    assert seen["events"] == [20.0, 25.0, 30.0, 10.0, 12.0]


def test_shuffled_input_matches_sorted_input_through_real_core_ewma() -> None:
    ordered = _run(_history(), datetime(2026, 6, 3, tzinfo=UTC))
    shuffled = _run(_history().iloc[[2, 0, 1, 4, 3]], datetime(2026, 6, 3, tzinfo=UTC))
    pd.testing.assert_frame_equal(ordered, shuffled)


def test_real_core_ewma_returns_a_rate_and_a_positive_ess() -> None:
    result = _run(_history(), datetime(2026, 6, 3, tzinfo=UTC))
    # EW(events)/EW(opportunities) is a weighted average of the per-row rates
    # (weights = decay x opportunities), so it must sit between their extremes.
    per_row = [20.0 / 9.0, 25.0 / 12.0, 30.0 / 15.0]
    assert min(per_row) <= result.loc[1, RATE] <= max(per_row)
    assert result.loc[1, EFFECTIVE_SAMPLE_SIZE] > 0.0


def test_empty_history_returns_empty_frame() -> None:
    empty = pd.DataFrame(columns=["pitcher_id", "pitches", "outs", "captured_at_utc"])
    result = _run(empty, datetime(2026, 6, 3, tzinfo=UTC))
    assert result.empty
