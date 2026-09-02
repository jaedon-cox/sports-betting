"""Pitch-level -> per-game aggregates.

The assertions that matter are the classification rules: what counts as a CSW,
which events record how many outs, who is the starter, and which side was
batting. Each is a place where a plausible-looking mistake produces numbers
that are wrong by a few percent and look entirely normal.
"""

from __future__ import annotations

import pandas as pd
import pytest

from sbm.sports.mlb.ingest.statcast_games import (
    OUT_EVENTS,
    XWOBA,
    aggregate_pitcher_games,
    aggregate_team_batting_games,
)


def pitch(**overrides) -> dict:
    base = {
        "game_pk": 1, "game_date": "2026-08-30", "pitcher": 100, "batter": 500,
        "p_throws": "R", "stand": "L", "description": "ball", "events": None,
        "bb_type": None, "inning": 1, "inning_topbot": "Top",
        "home_team": "NYY", "away_team": "BOS", "at_bat_number": 1,
        XWOBA: None,
    }
    return {**base, **overrides}


def frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


# -- CSW ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "is_csw"),
    [
        ("called_strike", True),
        ("swinging_strike", True),
        ("swinging_strike_blocked", True),
        ("foul_tip", False),
        ("foul", False),
        ("ball", False),
        ("hit_into_play", False),
    ],
)
def test_csw_counts_called_strikes_and_whiffs_only(description: str, is_csw: bool) -> None:
    """`foul_tip` is contact, not a miss — matching `savant.py`'s definition.
    Counting it would inflate every pitcher's CSW% by roughly a point."""
    out = aggregate_pitcher_games(frame(pitch(description=description)))
    assert int(out.iloc[0]["csw"]) == (1 if is_csw else 0)


# -- outs -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("event", "outs"),
    [
        ("field_out", 1), ("strikeout", 1), ("force_out", 1), ("sac_fly", 1),
        ("grounded_into_double_play", 2), ("double_play", 2),
        ("strikeout_double_play", 2), ("triple_play", 3),
        ("single", 0), ("walk", 0), ("home_run", 0), ("field_error", 0),
    ],
)
def test_outs_are_counted_by_event(event: str, outs: int) -> None:
    out = aggregate_pitcher_games(frame(pitch(events=event)))
    assert int(out.iloc[0]["outs"]) == outs


def test_fielders_choice_records_no_out_but_fielders_choice_out_does() -> None:
    """Statcast uses `fielders_choice` when the batter reaches and
    `fielders_choice_out` for the retired runner. Counting both would
    double-count, and innings pitched is a denominator — an over-count would
    deflate every rate."""
    assert OUT_EVENTS.get("fielders_choice", 0) == 0
    assert OUT_EVENTS["fielders_choice_out"] == 1


# -- starter detection ----------------------------------------------------


def test_the_starter_is_whoever_faced_the_first_batter() -> None:
    """Derived from `at_bat_number`, not row order: a pitcher's rows group by
    game, not by appearance sequence."""
    out = aggregate_pitcher_games(
        frame(
            pitch(pitcher=200, at_bat_number=40, events="single"),
            pitch(pitcher=100, at_bat_number=1, events="strikeout"),
        )
    )
    starts = dict(zip(out["pitcher"], out["is_start"]))
    assert starts[100] is True and starts[200] is False


def test_each_side_gets_its_own_starter() -> None:
    """Two clubs, two starters — the minimum is per (game, pitching club),
    never per game."""
    out = aggregate_pitcher_games(
        frame(
            pitch(pitcher=100, at_bat_number=1, inning_topbot="Top"),
            pitch(pitcher=200, at_bat_number=2, inning_topbot="Bot"),
            pitch(pitcher=300, at_bat_number=9, inning_topbot="Top"),
        )
    )
    assert int(out["is_start"].sum()) == 2


# -- sides ----------------------------------------------------------------


def test_top_of_the_inning_means_the_home_club_is_pitching() -> None:
    """Statcast states this only as the half-inning label; getting it backwards
    would attribute every pitching line to the wrong club."""
    out = aggregate_pitcher_games(frame(pitch(inning_topbot="Top")))
    assert out.iloc[0]["pitching_team"] == "NYY"
    out = aggregate_pitcher_games(frame(pitch(inning_topbot="Bot")))
    assert out.iloc[0]["pitching_team"] == "BOS"


def test_batted_ball_types_are_split_out() -> None:
    out = aggregate_pitcher_games(
        frame(
            pitch(events="field_out", bb_type="ground_ball"),
            pitch(events="field_out", bb_type="fly_ball"),
            pitch(events="double", bb_type="line_drive"),
            pitch(events="field_out", bb_type="popup"),
        )
    )
    row = out.iloc[0]
    assert (row["ground_balls"], row["fly_balls"], row["line_drives"], row["popups"]) == (1, 1, 1, 1)


# -- team batting ---------------------------------------------------------


def test_batting_rows_split_by_the_hand_faced() -> None:
    """A club that sees a righty and a lefty in one game produces two rows —
    `features/offense.py` resolves the split against tonight's starter."""
    out = aggregate_team_batting_games(
        frame(
            pitch(p_throws="R", events="single", **{XWOBA: 0.5}),
            pitch(p_throws="L", events="strikeout", **{XWOBA: 0.0}),
        )
    )
    assert sorted(out["opp_hand"]) == ["L", "R"]
    assert set(out["batting_team"]) == {"BOS"}  # Top of the inning: away bats


def test_plate_appearances_without_an_xwoba_are_excluded() -> None:
    """The four events Savant leaves null — catcher_interf, intent_walk,
    sac_bunt, truncated_pa — are exactly those wOBA excludes, so dropping them
    is the correct denominator rather than an approximation."""
    out = aggregate_team_batting_games(
        frame(
            pitch(events="single", **{XWOBA: 0.9}),
            pitch(events="sac_bunt", **{XWOBA: None}),
        )
    )
    assert int(out.iloc[0]["plate_appearances"]) == 1
    assert float(out.iloc[0]["xwoba_sum"]) == pytest.approx(0.9)


def test_an_empty_pull_yields_empty_frames_rather_than_raising() -> None:
    """An off-day, or a window before the season — both are normal."""
    empty = pd.DataFrame()
    assert aggregate_pitcher_games(empty).empty
    assert aggregate_team_batting_games(empty).empty
