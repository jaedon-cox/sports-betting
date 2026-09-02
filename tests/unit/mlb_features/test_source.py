"""`PostgrestSnapshotSource` — the leakage boundary, and what it does with gaps.

Two things are worth pinning here above all else. First, that the as-of cut is
actually applied: the SQL enforces it, so what this asserts is that the source
*asks* for the right window and never widens it. Second, that missing data
arrives as NaN rather than a raise or a fabricated value — the whole feature
frame degrades to league averages in `columns.py`, which is the documented
behaviour, and anything else would either kill a slate or price it on invented
numbers.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from sbm.contracts.feature import AsOf
from sbm.sports.mlb.features.source import PostgrestSnapshotSource
from sbm.sports.mlb.features.source.context import GameContext
from sbm.sports.mlb.ingest.statsapi.venue import VenueInfo

AS_OF = AsOf(ts=datetime(2026, 9, 1, 22, 45, tzinfo=UTC))
PARK = VenueInfo(7, "Park", 40.8, -73.9, 45.0, "Retractable", "Grass")


class FakeClient:
    """Records every RPC and answers from a scripted mapping."""

    def __init__(self, results: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._results = results or {}

    def rpc(self, name: str, params: dict):
        self.calls.append((name, params))
        return self._results.get(name, [])

    def params_for(self, name: str) -> dict:
        return next(p for n, p in self.calls if n == name)


def context(**overrides) -> GameContext:
    base = dict(
        external_id="555", internal_id=101, home_team="NYY", away_team="BOS",
        home_team_id=11, away_team_id=22,
        home_starter_id="100", away_starter_id="200", venue=PARK,
    )
    return GameContext(**{**base, **overrides})


def source(client: FakeClient, ctx: GameContext | None = None) -> PostgrestSnapshotSource:
    game = ctx or context()
    return PostgrestSnapshotSource(client=client, games={game.external_id: game})


def pitcher_row(player_id: str, game_date: str, **overrides) -> dict:
    base = {
        "player_id": player_id, "game_date": game_date, "throws": "R", "is_start": True,
        "pitches": 95, "csw": 27, "batters_faced": 24, "outs": 18, "strikeouts": 6,
        "walks": 2, "hit_by_pitch": 0, "home_runs": 1, "ground_balls": 7,
        "fly_balls": 5, "line_drives": 3, "popups": 1, "siera": None,
    }
    return {**base, **overrides}


# -- the as-of cut --------------------------------------------------------


def test_the_form_window_is_asked_for_strictly_before_the_as_of_date() -> None:
    """A game on the slate date has not finished when a pick locks at T-45min,
    so including it would price tonight partly on tonight's result."""
    client = FakeClient()
    source(client).pitcher_inputs(["555"], AS_OF)
    params = client.params_for("fn_pitcher_game_form")
    assert params["p_as_of"] == "2026-09-01"
    assert params["p_from"] < params["p_as_of"]


def test_only_this_slate_s_starters_are_requested() -> None:
    client = FakeClient()
    source(client).pitcher_inputs(["555"], AS_OF)
    assert client.params_for("fn_pitcher_game_form")["p_player_ids"] == ["100", "200"]


def test_the_injury_read_is_bounded_on_both_ends() -> None:
    """Absence is what marks a player available, so a stale row older than the
    club's last sweep describes someone since reinstated."""
    client = FakeClient()
    source(client).pitcher_inputs(["555"], AS_OF)
    params = client.params_for("fn_injury_status_asof")
    assert params["p_as_of"] == AS_OF.ts.isoformat()
    assert params["p_since"] < params["p_as_of"]


# -- gaps degrade, never raise -------------------------------------------


def test_a_starter_with_no_history_yields_nan_not_an_error() -> None:
    """A debut, or a slate priced before the stat job has run. `columns.py`
    substitutes the league-average prior downstream."""
    home, away = source(FakeClient()).pitcher_inputs(["555"], AS_OF)
    assert np.isnan(home.loc["555", "xfip"])
    assert home.loc["555", "hand"] is None


def test_a_game_off_this_slate_becomes_a_row_of_nan(recwarn) -> None:
    """`build()` reindexes to `game_ids`; an unknown id must not raise."""
    home, _ = source(FakeClient()).pitcher_inputs(["555", "999"], AS_OF)
    assert list(home.index) == ["555", "999"]
    assert home.loc["999"].isna().all()


def test_a_game_with_no_probable_pitcher_is_priced_anyway() -> None:
    """Routine hours before first pitch — the slate is priced on what is known
    at `as_of`, not refused."""
    ctx = context(home_starter_id=None)
    home, _ = source(FakeClient(), ctx).pitcher_inputs(["555"], AS_OF)
    assert bool(home.loc["555", "starter_injured"]) is False
    assert np.isnan(home.loc["555", "xfip"])


def test_siera_is_null_by_design_so_the_xfip_fallback_carries_every_row() -> None:
    """SIERA is a FanGraphs formula and FanGraphs answers 403
    (statcast_games.py::DEFERRED)."""
    client = FakeClient({"fn_pitcher_game_form": [pitcher_row("100", "2026-08-20")]})
    home, _ = source(client).pitcher_inputs(["555"], AS_OF)
    assert np.isnan(home.loc["555", "siera"])
    assert not np.isnan(home.loc["555", "xfip"])


def test_wrc_plus_is_null_by_design_and_offense_rides_on_xwoba() -> None:
    home, _ = source(FakeClient()).offense_inputs(["555"], AS_OF)
    assert np.isnan(home.loc["555", "wrc_plus"])


# -- real values reach the frame -----------------------------------------


def test_a_starter_with_history_gets_real_rates() -> None:
    rows = [pitcher_row("100", f"2026-08-{day:02d}") for day in (10, 16, 22, 28)]
    client = FakeClient({"fn_pitcher_game_form": rows})
    home, _ = source(client).pitcher_inputs(["555"], AS_OF)
    row = home.loc["555"]
    assert row["hand"] == "R"
    assert 0.0 < row["csw_pct"] < 1.0
    assert 0.0 < row["gb_pct"] < 1.0
    assert row["innings_pitched"] == pytest.approx(24.0)  # 4 starts x 18 outs / 3
    assert 1.0 < row["xfip"] < 9.0


def test_the_injured_flag_is_set_from_the_injury_read() -> None:
    client = FakeClient(
        {
            "fn_pitcher_game_form": [pitcher_row("100", "2026-08-20")],
            "fn_injury_status_asof": [{"player_id": "100", "team_id": 11, "status": "D15"}],
        }
    )
    home, away = source(client).pitcher_inputs(["555"], AS_OF)
    # pandas stores these as numpy bools; `bool()` is the honest comparison.
    assert bool(home.loc["555", "starter_injured"]) is True
    assert bool(away.loc["555", "starter_injured"]) is False


def test_the_platoon_split_resolves_against_the_opposing_starter_s_hand() -> None:
    """`home_off_xwoba_vs_opp_hand` must reflect the AWAY starter's hand."""
    client = FakeClient(
        {
            "fn_pitcher_game_form": [
                pitcher_row("100", "2026-08-20", throws="R"),
                pitcher_row("200", "2026-08-20", throws="L"),
            ],
            "fn_team_batting_form": [
                {"batting_team": "NYY", "game_date": "2026-08-20", "opp_hand": "L",
                 "plate_appearances": 38, "xwoba_sum": 12.5},
                {"batting_team": "NYY", "game_date": "2026-08-20", "opp_hand": "R",
                 "plate_appearances": 38, "xwoba_sum": 9.0},
            ],
        }
    )
    home, _ = source(client).offense_inputs(["555"], AS_OF)
    # Away starter throws L, so home's split is the vs-L row: 12.5/38.
    assert home.loc["555", "xwoba_vs_opp_hand"] == pytest.approx(12.5 / 38, rel=1e-3)


# -- park and weather -----------------------------------------------------


def test_park_run_factor_is_null_because_no_free_source_exists() -> None:
    """pybaseball's park_codes() returns Retrosheet ids and is broken upstream.
    A guessed 1.0 would read as "neutral park" rather than "unknown"."""
    park = source(FakeClient()).park_inputs(["555"], AS_OF)
    assert np.isnan(park.loc["555", "run_factor"])
    assert park.loc["555", "roof_type"] == "Retractable"
    assert park.loc["555", "orientation_deg"] == 45.0


def test_weather_joins_on_the_internal_game_id() -> None:
    """`weather_snapshots` is keyed on the surrogate while `game_ids` here are
    gamePks — `GameContext.internal_id` is the only bridge."""
    client = FakeClient(
        {"fn_weather_asof": [
            {"game_id": 101, "temp_f": 78.0, "wind_mph": 9.0,
             "wind_dir_deg": 180, "precip_pct": 5.0}
        ]}
    )
    out = source(client).weather_inputs(["555"], AS_OF)
    assert out.loc["555", "temp_f"] == 78.0
    assert client.params_for("fn_weather_asof")["p_game_ids"] == [101]


def test_a_game_with_no_forecast_is_nan_not_zero() -> None:
    """Zero degrees is a temperature; missing is not."""
    out = source(FakeClient()).weather_inputs(["555"], AS_OF)
    assert np.isnan(out.loc["555", "temp_f"])
    assert out.loc["555", "park_orientation_deg"] == 45.0


def test_a_venue_lookup_that_failed_leaves_park_columns_null() -> None:
    out = source(FakeClient(), context(venue=None)).park_inputs(["555"], AS_OF)
    assert out.loc["555", "roof_type"] is None


# -- caching --------------------------------------------------------------


def test_the_starter_history_is_read_once_per_build() -> None:
    """`build()` calls all six methods for one slate at one instant; three of
    them need the same history."""
    client = FakeClient()
    src = source(client)
    src.pitcher_inputs(["555"], AS_OF)
    src.offense_inputs(["555"], AS_OF)
    src.tto_inputs(["555"], AS_OF)
    assert sum(1 for n, _ in client.calls if n == "fn_pitcher_game_form") == 1


def test_lookup_keys_are_coerced_to_text_so_a_numeric_id_cannot_miss() -> None:
    """A numeric `player_id` against a string key is absent, not an error — the
    whole slate would silently price as league-average."""
    rows = [pitcher_row(100, "2026-08-20")]  # int, not str
    client = FakeClient({"fn_pitcher_game_form": rows})
    home, _ = source(client).pitcher_inputs(["555"], AS_OF)
    assert not np.isnan(home.loc["555", "xfip"])


# -- the bullpen path with real rows --------------------------------------
#
# Every bullpen assertion above ran against an EMPTY result, which returns
# early before a single column is read — which is exactly how a missing `csw`
# in fn_bullpen_game_form reached production. These feed it real rows.


def bullpen_row(team: str, game_date: str, **overrides) -> dict:
    base = {
        "pitching_team": team, "game_date": game_date, "appearances": 3,
        "pitches": 48, "csw": 14, "outs": 9, "batters_faced": 12, "strikeouts": 4,
        "walks": 1, "hit_by_pitch": 0, "home_runs": 0, "ground_balls": 4,
        "fly_balls": 3, "line_drives": 1, "popups": 1,
    }
    return {**base, **overrides}


def test_bullpen_rates_are_computed_from_real_rows() -> None:
    rows = [bullpen_row("NYY", f"2026-08-{d:02d}") for d in (25, 27, 29, 31)]
    client = FakeClient({"fn_bullpen_game_form": rows})
    home, away = source(client).bullpen_inputs(["555"], AS_OF)
    assert 1.0 < home.loc["555", "xfip"] < 9.0
    assert np.isnan(away.loc["555", "xfip"])  # BOS has no rows


def test_a_read_missing_a_column_fails_naming_it() -> None:
    """The production failure was `KeyError: 'csw'` from inside recency.py, with
    nothing pointing at the SQL. It must name the column and the migration."""
    rows = [{k: v for k, v in bullpen_row("NYY", "2026-08-29").items() if k != "csw"}]
    client = FakeClient({"fn_bullpen_game_form": rows})
    with pytest.raises(KeyError, match="missing \\['csw'\\]"):
        source(client).bullpen_inputs(["555"], AS_OF)


def test_fatigue_is_a_zero_centred_index_not_a_pitch_count() -> None:
    """`mean.py` adds this in LOG space — raw pitches per day produced
    exp(0.05 * 57) and a 46-run projection."""
    from sbm.sports.mlb.features.source.derive import (
        FATIGUE_WINDOW_DAYS,
        NORMAL_RELIEF_PITCHES_PER_DAY,
    )

    normal = NORMAL_RELIEF_PITCHES_PER_DAY * FATIGUE_WINDOW_DAYS
    rows = [bullpen_row("NYY", "2026-08-31", pitches=int(normal))]
    client = FakeClient({"fn_bullpen_game_form": rows})
    home, _ = source(client).bullpen_inputs(["555"], AS_OF)
    assert home.loc["555", "fatigue"] == pytest.approx(0.0, abs=0.05)


def test_an_overworked_pen_scores_positive() -> None:
    rows = [bullpen_row("NYY", "2026-08-31", pitches=300)]
    client = FakeClient({"fn_bullpen_game_form": rows})
    home, _ = source(client).bullpen_inputs(["555"], AS_OF)
    assert home.loc["555", "fatigue"] > 1.0
