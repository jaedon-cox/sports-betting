"""The output contract: one `line_snapshots` row, and the de-vig vocabulary.

This module knows `db`'s schema and nothing about The Odds API's wire format
(that's `parse.py`). A migration to `line_snapshots` should land here and
nowhere else in the package.

**De-vig method**: `power` for ALL THREE markets, not split by market
(`main`'s finding, confirmed twice by `core`: additive/multiplicative's
model doc §7 rationale didn't survive a 50k-book simulation, and a per-market
split would mix de-vig artifacts into blended CLV). `db` keeps a per-market
`devig_method` column for a future re-split, which is why the value travels
on the row rather than being assumed at write time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

Market = Literal["moneyline", "total", "spread"]
"""Persisted market keys. `spread` — not `run_line` — carries MLB's run line:
that is `markets/spread.py` with line=+/-1.5, and CLAUDE.md rule 7 says shared
code must not learn one sport's product names. `db/migrations/003_picks.sql`
deliberately left the column un-enum'd for the same reason."""

DEVIG_METHOD = "power"
"""The one method for all three markets (see module docstring)."""


class DevigFn(Protocol):
    """`core.pricing.devig.devig_sides`'s shape — `method` is keyword-only.

    Injectable so tests don't need `core` wired, and so a future per-market
    re-split is a one-line change at the call site rather than a rewrite.
    """

    def __call__(self, prices_by_side: dict[str, int], *, method: str) -> dict[str, float]: ...


@dataclass(frozen=True, slots=True)
class LineSnapshotRow:
    """Normalized row ready for `sbm.store.snapshots.insert_line_snapshots`.

    Field-for-field mappable onto `db`'s writer-side row. `devig_method`
    rides along with `implied_prob_devigged` rather than being left to the
    caller because migration 004 constrains the two to be null or non-null
    together, and `line_snapshots` is append-only: a backtest has to be able
    to prove which method produced a stored number even after `DEVIG_METHOD`
    changes. Emitting the probability without the method would make every row
    this package produces violate that CHECK.

    `game_id` is `db`'s internal `games.id`, NOT the external StatsAPI
    gamePk — see `odds/resolution.py`.
    """

    game_id: int
    market: Market
    side: str
    line: float | None
    price_american: int
    implied_prob_devigged: float
    captured_at_utc: datetime
    is_closing: bool
    devig_method: str = DEVIG_METHOD
    source: str = "pinnacle"
