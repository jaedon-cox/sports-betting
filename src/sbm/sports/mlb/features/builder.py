"""Wires ingest sources into `contracts.feature.FeatureBuilder` — the
leakage boundary the whole system depends on: the exact same `build()` runs
for live production (`as_of` = now) and backtest reconstruction (`as_of` =
some historical instant), so there is no separate backtest code path to
silently diverge from production.

`SnapshotSource` is the one injected seam: point-in-time reads over stored
snapshots (`WHERE captured_at_utc <= as_of ORDER BY captured_at_utc DESC
LIMIT 1`, backend doc §3.2). This package doesn't own that implementation —
`db`/`store` does, and as of writing `store/` is write-only (confirmed with
`db`: "no REST read layer in this package"), so no real `SnapshotSource`
exists yet anywhere in the repo. `MLBFeatureBuilder()` is still
zero-arg-constructible (`vertical.py` calls it that way) via
`_UnwiredSnapshotSource`, which fails loud on first use rather than
fabricating data — see its docstring. Pass a real `source=` once one exists.

Wherever a `SnapshotSource` method needs genuine recency-weighting over raw
history (currently: bullpen fatigue, from `ingest/savant.py`'s per-appearance
pitch data), it should use `features/recency.py`'s `recency_weighted_by_entity`,
which is now bound to `core`'s shipped `sbm.core.recency.ewma_asof`. Note that
it takes *events* and *opportunities* as separate columns and returns
`(rate, effective_sample_size)` per entity — the num/denom-weighted-separately
rule (model doc §4.6) can't be expressed with a single pre-divided rate column.
This module itself does no recency math, only assembly.

Known v1 gaps (flagged to `model`/`main`, not silently worked around):
- No lineup-order ingest yet, so "confirmed-lineup delta vs projected"
  (model doc §10.2) has no source and isn't a column here.
- Umpire run-environment (doc §10.3, CONDITIONAL) has no assigned ingest
  source in the backend plan at all — omitted, not approximated.
- `park_run_factor` is present but expected mostly null (see `features/park.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import pandas as pd

from sbm.contracts.feature import AsOf
from sbm.sports.mlb.features.bullpen import compute_bullpen_features
from sbm.sports.mlb.features.offense import compute_offense_features
from sbm.sports.mlb.features.park import compute_park_features
from sbm.sports.mlb.features.pitcher import compute_pitcher_features
from sbm.sports.mlb.features.tto import compute_tto_features
from sbm.sports.mlb.features.weather import compute_weather_features

SideFrames = tuple[pd.DataFrame, pd.DataFrame]
"""(home, away), each indexed by game_id with one feature family's required columns."""


@runtime_checkable
class SnapshotSource(Protocol):
    """One method per feature family, each already point-in-time filtered to
    `as_of` and already split into home/away where the family needs it.

    Every method must satisfy the same leakage rule `AsOf` documents: no row
    with `captured_at_utc > as_of.ts` may influence the result.
    """

    def pitcher_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames: ...
    def bullpen_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames: ...
    def offense_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames: ...
    def tto_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames: ...
    def park_inputs(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame: ...
    def weather_inputs(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame: ...


_UNWIRED_SOURCE_ERROR = (
    "MLBFeatureBuilder has no point-in-time snapshot source wired yet — "
    "sbm.store is write-only as of writing (confirmed with `db`: no read "
    "layer exists), so there is nothing real to default to. Pass a real "
    "SnapshotSource explicitly: MLBFeatureBuilder(source=my_source)."
)


class _UnwiredSnapshotSource:
    """Placeholder default so `MLBFeatureBuilder()` is constructible with zero
    args — `vertical.py.feature_builder()` calls it that way — without
    silently returning fabricated data. Every method raises instead of
    guessing; this is the "honest placeholder," not a working implementation.
    """

    def pitcher_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames:
        raise NotImplementedError(_UNWIRED_SOURCE_ERROR)

    def bullpen_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames:
        raise NotImplementedError(_UNWIRED_SOURCE_ERROR)

    def offense_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames:
        raise NotImplementedError(_UNWIRED_SOURCE_ERROR)

    def tto_inputs(self, game_ids: list[str], as_of: AsOf) -> SideFrames:
        raise NotImplementedError(_UNWIRED_SOURCE_ERROR)

    def park_inputs(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame:
        raise NotImplementedError(_UNWIRED_SOURCE_ERROR)

    def weather_inputs(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame:
        raise NotImplementedError(_UNWIRED_SOURCE_ERROR)


@dataclass(frozen=True, slots=True)
class MLBFeatureBuilder:
    """Satisfies `contracts.feature.FeatureBuilder`."""

    source: SnapshotSource = field(default_factory=_UnwiredSnapshotSource)

    def build(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame:
        home_p, away_p = self.source.pitcher_inputs(game_ids, as_of)
        home_b, away_b = self.source.bullpen_inputs(game_ids, as_of)
        home_o, away_o = self.source.offense_inputs(game_ids, as_of)
        home_t, away_t = self.source.tto_inputs(game_ids, as_of)
        park = self.source.park_inputs(game_ids, as_of)
        weather = self.source.weather_inputs(game_ids, as_of)

        frames = (
            compute_pitcher_features(home_p, away_p),
            compute_bullpen_features(home_b, away_b),
            compute_offense_features(home_o, away_o),
            compute_tto_features(home_t, away_t),
            compute_park_features(park),
            compute_weather_features(weather),
        )
        out = frames[0]
        for frame in frames[1:]:
            out = out.join(frame, how="outer")
        # Market odds are never a column here (model doc A1) — nothing above
        # ever reads `line_snapshots`/`odds/`, by construction, not by filter.
        return out.reindex(game_ids)
