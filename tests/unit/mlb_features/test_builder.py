"""builder.py wiring — a fake SnapshotSource stands in for `db`'s real
implementation, which doesn't exist yet."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from sbm.contracts.feature import AsOf, FeatureBuilder
from sbm.sports.mlb.features.builder import MLBFeatureBuilder

GAME_IDS = ["g1"]
IDX = pd.Index(GAME_IDS, name="game_id")


class FakeSnapshotSource:
    def pitcher_inputs(self, game_ids, as_of):
        home = pd.DataFrame(
            {
                "siera": [3.1], "xfip": [3.5], "csw_pct": [0.30], "gb_pct": [0.45],
                "hand": ["R"], "innings_pitched": [120.0], "starter_injured": [False],
            },
            index=IDX,
        )
        away = pd.DataFrame(
            {
                "siera": [4.0], "xfip": [4.2], "csw_pct": [0.27], "gb_pct": [0.38],
                "hand": ["L"], "innings_pitched": [100.0], "starter_injured": [False],
            },
            index=IDX,
        )
        return home, away

    def bullpen_inputs(self, game_ids, as_of):
        home = pd.DataFrame({"fatigue": [40.0], "xfip": [3.9], "unavailable_arms": [0]}, index=IDX)
        away = pd.DataFrame({"fatigue": [20.0], "xfip": [4.1], "unavailable_arms": [1]}, index=IDX)
        return home, away

    def offense_inputs(self, game_ids, as_of):
        home = pd.DataFrame(
            {"wrc_plus": [110], "xwoba_vs_opp_hand": [0.33], "key_injuries_count": [0]}, index=IDX
        )
        away = pd.DataFrame(
            {"wrc_plus": [95], "xwoba_vs_opp_hand": [0.31], "key_injuries_count": [1]}, index=IDX
        )
        return home, away

    def tto_inputs(self, game_ids, as_of):
        home = pd.DataFrame({"expected_ip": [5.8], "scheduled_innings": [9]}, index=IDX)
        away = pd.DataFrame({"expected_ip": [6.1], "scheduled_innings": [9]}, index=IDX)
        return home, away

    def park_inputs(self, game_ids, as_of):
        return pd.DataFrame(
            {"run_factor": [None], "roof_type": ["Open"], "turf_type": ["Grass"], "orientation_deg": [9.0]},
            index=IDX,
        )

    def weather_inputs(self, game_ids, as_of):
        return pd.DataFrame(
            {
                "wind_mph": [8.0], "wind_dir_deg": [200.0], "temp_f": [72.0],
                "precip_pct": [10.0], "park_orientation_deg": [9.0],
            },
            index=IDX,
        )


def test_builder_satisfies_the_feature_builder_contract() -> None:
    builder = MLBFeatureBuilder(source=FakeSnapshotSource())
    assert isinstance(builder, FeatureBuilder)


def test_zero_arg_construction_succeeds_but_build_fails_loud() -> None:
    """vertical.py calls `MLBFeatureBuilder()` with no args — construction
    must succeed (no real SnapshotSource exists yet, sbm.store is
    write-only), but calling build() must raise clearly rather than
    fabricate data."""
    builder = MLBFeatureBuilder()
    assert isinstance(builder, FeatureBuilder)
    with pytest.raises(NotImplementedError, match="no point-in-time snapshot source"):
        builder.build(GAME_IDS, AsOf(ts=datetime(2026, 8, 29, tzinfo=UTC)))


def test_build_assembles_one_row_per_game_with_all_family_columns() -> None:
    builder = MLBFeatureBuilder(source=FakeSnapshotSource())
    as_of = AsOf(ts=datetime(2026, 8, 29, 12, 0, tzinfo=UTC))
    out = builder.build(GAME_IDS, as_of)

    assert list(out.index) == GAME_IDS
    for expected_col in (
        "home_starter_siera",
        "away_bullpen_fatigue",
        "home_off_wrc_plus",
        "away_bullpen_exposure_ip",
        "park_run_factor",
        "wind_out_component_mph",
    ):
        assert expected_col in out.columns

    # Market odds must never appear as a feature column (model doc A1).
    assert not any("odds" in c or "market" in c for c in out.columns)


def test_build_preserves_game_id_order_via_reindex() -> None:
    class TwoGameSource(FakeSnapshotSource):
        def pitcher_inputs(self, game_ids, as_of):
            idx = pd.Index(game_ids, name="game_id")
            home = pd.DataFrame(
                {
                    "siera": [3.1, 3.2], "xfip": [3.5, 3.6], "csw_pct": [0.30, 0.29], "gb_pct": [0.45, 0.44],
                    "hand": ["R", "R"], "innings_pitched": [120.0, 100.0], "starter_injured": [False, False],
                },
                index=idx,
            )
            away = pd.DataFrame(
                {
                    "siera": [4.0, 3.9], "xfip": [4.2, 4.1], "csw_pct": [0.27, 0.28], "gb_pct": [0.38, 0.39],
                    "hand": ["L", "L"], "innings_pitched": [100.0, 90.0], "starter_injured": [False, False],
                },
                index=idx,
            )
            return home, away

        def bullpen_inputs(self, game_ids, as_of):
            idx = pd.Index(game_ids, name="game_id")
            home = pd.DataFrame({"fatigue": [40.0, 41.0], "xfip": [3.9, 3.8], "unavailable_arms": [0, 0]}, index=idx)
            away = pd.DataFrame({"fatigue": [20.0, 21.0], "xfip": [4.1, 4.0], "unavailable_arms": [1, 0]}, index=idx)
            return home, away

        def offense_inputs(self, game_ids, as_of):
            idx = pd.Index(game_ids, name="game_id")
            home = pd.DataFrame(
                {"wrc_plus": [110, 111], "xwoba_vs_opp_hand": [0.33, 0.34], "key_injuries_count": [0, 0]}, index=idx
            )
            away = pd.DataFrame(
                {"wrc_plus": [95, 96], "xwoba_vs_opp_hand": [0.31, 0.32], "key_injuries_count": [1, 1]}, index=idx
            )
            return home, away

        def tto_inputs(self, game_ids, as_of):
            idx = pd.Index(game_ids, name="game_id")
            home = pd.DataFrame({"expected_ip": [5.8, 5.9], "scheduled_innings": [9, 9]}, index=idx)
            away = pd.DataFrame({"expected_ip": [6.1, 6.0], "scheduled_innings": [9, 9]}, index=idx)
            return home, away

        def park_inputs(self, game_ids, as_of):
            idx = pd.Index(game_ids, name="game_id")
            return pd.DataFrame(
                {"run_factor": [None, None], "roof_type": ["Open", "Dome"], "turf_type": ["Grass", "Artificial"], "orientation_deg": [9.0, 45.0]},
                index=idx,
            )

        def weather_inputs(self, game_ids, as_of):
            idx = pd.Index(game_ids, name="game_id")
            return pd.DataFrame(
                {
                    "wind_mph": [8.0, 5.0], "wind_dir_deg": [200.0, 100.0], "temp_f": [72.0, 68.0],
                    "precip_pct": [10.0, 0.0], "park_orientation_deg": [9.0, 45.0],
                },
                index=idx,
            )

    builder = MLBFeatureBuilder(source=TwoGameSource())
    as_of = AsOf(ts=datetime(2026, 8, 29, 12, 0, tzinfo=UTC))
    out = builder.build(["g2", "g1"], as_of)
    assert list(out.index) == ["g2", "g1"]
