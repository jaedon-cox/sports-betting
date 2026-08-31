"""The one place `core`'s EWMA gets invoked to collapse a raw per-entity
history into a single point-in-time value — kept apart from `builder.py` so
whoever implements `SnapshotSource` (that's `db`/`store`, since it's the one
with direct access to raw per-entity history behind the storage layer) can
import and reuse this without pulling in the rest of the feature-assembly
wiring.

**Now bound to `core`'s shipped `sbm.core.recency.ewma_asof`**, replacing this
module's earlier best-guess `EwmaFn`. The guess was wrong in three ways that
mattered, so this is a signature change, not a swapped import:

1. It took a single `values` column. `core` takes `events` and `opportunities`
   separately because an EWMA rate is `EW(events) / EW(opportunities)` — the
   num/denom-weighted-separately rule (model doc §4.6, §10.1). A single
   pre-divided per-row rate cannot express it, so the old shape structurally
   could not produce the locked weighting.
2. It passed `as_of` and the timestamp column down into `core`. `core` takes
   neither: "filtering/ordering is the feature layer's job, not core's". That
   job is this module's, and it is now done here — see the sort/filter below.
3. It returned one scalar. `core` returns `(rate, effective_sample_size)`;
   ESS is what model doc §5.4 shrinks thin histories by (early season, a
   newly-promoted arm), so dropping it would discard the shrinkage input.

`ewma` stays injectable so tests can assert the wiring without `core`'s
numerics in the loop.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import numpy as np
import pandas as pd

from sbm.core.recency import ewma_asof

EwmaFn = Callable[[np.ndarray, np.ndarray, float], tuple[float, float]]
"""(events, opportunities, half_life_games) -> (rate, effective_sample_size).

Matches `sbm.core.recency.ewma_asof`. Rows must already be chronological and
point-in-time filtered — `recency_weighted_by_entity` guarantees both before
calling this.
"""

RATE = "rate"
EFFECTIVE_SAMPLE_SIZE = "effective_sample_size"


def recency_weighted_by_entity(
    history: pd.DataFrame,
    *,
    entity_col: str,
    events_col: str,
    opportunities_col: str,
    captured_at_col: str,
    half_life_games: float,
    as_of: datetime,
    ewma: EwmaFn = ewma_asof,
) -> pd.DataFrame:
    """Collapse a raw per-appearance/per-start history into one recency-weighted
    `(rate, effective_sample_size)` per entity, indexed by `entity_col`.

    Two preconditions of `core`'s fold are enforced here rather than assumed,
    because `core` documents both as the feature layer's responsibility:

    - **Point-in-time** — rows with `captured_at_col > as_of` are dropped
      (CLAUDE.md rule 4). `SnapshotSource` is expected to have filtered
      already; re-applying it costs one comparison and means a source bug
      degrades a number rather than silently leaking the future into it.
    - **Chronological order** — `core.ewma_rate` decays by row position, so
      unordered input doesn't error, it returns a wrong number. Sorting here
      is what makes that unrepresentable.
    """
    empty = pd.DataFrame(columns=[RATE, EFFECTIVE_SAMPLE_SIZE], dtype=float)
    empty.index.name = entity_col
    if history.empty:
        return empty

    visible = history[history[captured_at_col] <= as_of]
    if visible.empty:
        return empty
    visible = visible.sort_values(captured_at_col, kind="stable")

    rows: dict[object, tuple[float, float]] = {}
    for entity, group in visible.groupby(entity_col, sort=False):
        rows[entity] = ewma(
            group[events_col].to_numpy(dtype=np.float64),
            group[opportunities_col].to_numpy(dtype=np.float64),
            half_life_games,
        )

    out = pd.DataFrame.from_dict(
        rows, orient="index", columns=[RATE, EFFECTIVE_SAMPLE_SIZE]
    ).astype(float)
    out.index.name = entity_col
    return out
