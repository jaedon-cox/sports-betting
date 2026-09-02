"""Job I — the window it covers, and the row conversion at the pandas boundary."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from sbm.jobs import job_i_statcast
from sbm.jobs.job_i_statcast import LOOKBACK_DAYS, _batting_row, _hand, _pitcher_row, _window
from sbm.store.game_stats import PITCHER_CONFLICT, TEAM_CONFLICT
from tests.unit.jobs.fakes import FakeClient, make_context


def test_the_default_window_ends_yesterday_and_covers_the_lookback(monkeypatch) -> None:
    """Ends yesterday because today's games have not been played; covers a
    trailing window because Statcast revises a game for a day or two after."""
    monkeypatch.delenv("SBM_BACKFILL_FROM", raising=False)
    monkeypatch.delenv("SBM_BACKFILL_TO", raising=False)
    start, end = _window(make_context())
    assert end == make_context().slate_date - pd.Timedelta(days=1).to_pytimedelta()
    assert (end - start).days == LOOKBACK_DAYS - 1


def test_both_backfill_bounds_drive_the_window(monkeypatch) -> None:
    monkeypatch.setenv("SBM_BACKFILL_FROM", "2025-04-01")
    monkeypatch.setenv("SBM_BACKFILL_TO", "2025-04-30")
    assert _window(make_context()) == (date(2025, 4, 1), date(2025, 4, 30))


@pytest.mark.parametrize("present", ["SBM_BACKFILL_FROM", "SBM_BACKFILL_TO"])
def test_half_a_backfill_range_is_refused(monkeypatch, present: str) -> None:
    """One bound alone is a typo, and treating it as "since the beginning of
    time" would pull two decades of pitch-level data on a mistyped input."""
    monkeypatch.delenv("SBM_BACKFILL_FROM", raising=False)
    monkeypatch.delenv("SBM_BACKFILL_TO", raising=False)
    monkeypatch.setenv(present, "2025-04-01")
    with pytest.raises(ValueError, match="must both be set or both unset"):
        _window(make_context())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("R", "R"), ("L", "L"), ("r", "R"), (None, None), ("", None), ("S", None), (float("nan"), None)],
)
def test_handedness_is_normalised_or_dropped(raw, expected) -> None:
    """`PitcherGameRow` rejects anything but L/R/None, mirroring 017's CHECK —
    so an unexpected value must become None here rather than fail a batch."""
    assert _hand(raw) == expected


def test_pitcher_rows_stringify_the_ids() -> None:
    """player_id and game_pk are TEXT in Postgres, and `player_id` has to join
    against `injury_snapshots.player_id`, which is also TEXT."""
    row = _pitcher_row(
        {
            "pitcher": 660271, "game_pk": 825040, "game_date": pd.Timestamp("2026-08-30"),
            "pitching_team": "NYY", "p_throws": "R", "is_start": True,
            "pitches": 95, "csw": 27, "batters_faced": 24, "outs": 18, "strikeouts": 6,
            "walks": 2, "hit_by_pitch": 0, "home_runs": 1, "ground_balls": 7,
            "fly_balls": 5, "line_drives": 3, "popups": 1,
        }
    )
    assert (row.player_id, row.game_pk) == ("660271", "825040")
    assert row.game_date == date(2026, 8, 30)
    assert row.siera is None  # deferred — FanGraphs is unreachable


def test_batting_rows_carry_the_split() -> None:
    row = _batting_row(
        {
            "game_pk": 825040, "game_date": "2026-08-30", "batting_team": "BOS",
            "opp_hand": "L", "plate_appearances": 38, "xwoba_sum": 11.4,
        }
    )
    assert (row.batting_team, row.opp_hand) == ("BOS", "L")
    assert row.xwoba_sum == pytest.approx(11.4)


def test_the_run_upserts_both_tables_on_their_natural_keys(monkeypatch) -> None:
    """Upsert, not insert: a re-pull must let Statcast's post-game revisions
    land rather than being rejected as a duplicate."""
    monkeypatch.delenv("SBM_BACKFILL_FROM", raising=False)
    monkeypatch.delenv("SBM_BACKFILL_TO", raising=False)
    monkeypatch.setattr(
        job_i_statcast, "_aggregate",
        lambda start, end: (
            [_pitcher_row({
                "pitcher": 1, "game_pk": 2, "game_date": "2026-08-30", "pitching_team": "NYY",
                "p_throws": "L", "is_start": False, "pitches": 12, "csw": 4,
                "batters_faced": 3, "outs": 3, "strikeouts": 1, "walks": 0,
                "hit_by_pitch": 0, "home_runs": 0, "ground_balls": 1, "fly_balls": 1,
                "line_drives": 0, "popups": 0,
            })],
            [_batting_row({
                "game_pk": 2, "game_date": "2026-08-30", "batting_team": "BOS",
                "opp_hand": "L", "plate_appearances": 3, "xwoba_sum": 0.9,
            })],
            False,
        ),
    )
    client = FakeClient()
    summary = job_i_statcast.run(make_context(client))
    tables = {table: conflict for table, _, conflict in client.upserts}
    assert tables["pitcher_game_stats"] == PITCHER_CONFLICT
    assert tables["team_batting_game_stats"] == TEAM_CONFLICT
    assert "1 pitcher-game rows" in summary


def test_a_stale_cache_is_reported_in_the_summary(monkeypatch) -> None:
    """A green run served from disk is not the same as a fresh pull, and the
    operator should be able to tell from the log line alone."""
    monkeypatch.delenv("SBM_BACKFILL_FROM", raising=False)
    monkeypatch.delenv("SBM_BACKFILL_TO", raising=False)
    monkeypatch.setattr(job_i_statcast, "_aggregate", lambda start, end: ([], [], True))
    assert "STALE CACHE" in job_i_statcast.run(make_context(FakeClient()))
