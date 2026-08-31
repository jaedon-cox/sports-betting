"""Point-in-time feature access — the leakage boundary.

The same builder serves live production and backtest reconstruction so the two
cannot silently diverge into different leakage regimes (backend doc §2.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

import pandas as pd


@dataclass(frozen=True, slots=True)
class AsOf:
    """The instant a feature row is allowed to know about.

    Any source row with `captured_at_utc > ts` is invisible. This is the single
    rule that makes backtest CLV trustworthy.
    """

    ts: datetime

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None or self.ts.utcoffset() != UTC.utcoffset(None):
            raise ValueError("AsOf.ts must be timezone-aware UTC")


@runtime_checkable
class FeatureBuilder(Protocol):
    """Builds the model input frame for a set of games at a point in time."""

    def build(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame:
        """One row per game_id, indexed by game_id.

        Must be deterministic given (game_ids, as_of) and must not read any
        snapshot captured after `as_of`. Market odds are never a column here —
        they live only in the edge/CLV layer (model doc A1).

        `game_ids` are the sport's own external, stable ids (MLB's gamePk),
        never a storage surrogate key. `db` numbers its rows for Postgres'
        benefit; that number means nothing to a model, and pinning it here
        would make every sport vertical depend on the shape of one table.
        Resolving external id <-> internal key is the store boundary's job.
        """
        ...
