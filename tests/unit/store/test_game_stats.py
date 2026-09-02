"""The two per-game fact writers: guards, JSON shaping, and conflict keys."""

from __future__ import annotations

from datetime import date

import pytest

from sbm.store.game_stats import (
    PITCHER_CONFLICT,
    TEAM_CONFLICT,
    PitcherGameRow,
    TeamBattingGameRow,
    upsert_pitcher_game_stats,
    upsert_team_batting_game_stats,
)


class _FakePostgrest:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[dict], str]] = []

    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> list[dict]:
        self.upserts.append((table, rows, on_conflict))
        return rows


def pitcher(**overrides) -> PitcherGameRow:
    base = dict(
        player_id="660271", game_pk="825040", game_date=date(2026, 8, 30),
        pitching_team="NYY", throws="R", is_start=True, pitches=95, csw=27,
        batters_faced=24, outs=18, strikeouts=6, walks=2, hit_by_pitch=0,
        home_runs=1, ground_balls=7, fly_balls=5, line_drives=3, popups=1,
    )
    return PitcherGameRow(**{**base, **overrides})


@pytest.mark.parametrize("hand", ["L", "R", None])
def test_valid_handedness_is_accepted(hand) -> None:
    assert pitcher(throws=hand).throws == hand


def test_an_unknown_hand_is_refused_naming_the_field() -> None:
    """Mirrors 017's CHECK locally: a bad value should fail here rather than as
    a PostgREST 400 partway through several thousand rows, where nothing says
    which row was wrong."""
    with pytest.raises(ValueError, match="throws must be one of"):
        pitcher(throws="S")


def test_an_unknown_opposing_hand_is_refused() -> None:
    with pytest.raises(ValueError, match="opp_hand must be one of"):
        TeamBattingGameRow(
            game_pk="1", game_date=date(2026, 8, 30), batting_team="BOS",
            opp_hand="S", plate_appearances=38, xwoba_sum=11.4,
        )


def test_siera_defaults_to_none() -> None:
    """NULL for every row this pipeline writes — SIERA is a FanGraphs formula
    and FanGraphs answers 403. The column exists so populating it later is a
    backfill, not a migration."""
    assert pitcher().siera is None


def test_dates_are_json_stringified() -> None:
    client = _FakePostgrest()
    upsert_pitcher_game_stats(client, [pitcher()])  # type: ignore[arg-type]
    assert client.upserts[0][1][0]["game_date"] == "2026-08-30"


def test_pitcher_rows_conflict_on_player_and_game() -> None:
    """A pitcher appears once per game; re-pulling the window must update that
    row rather than add a second."""
    client = _FakePostgrest()
    assert upsert_pitcher_game_stats(client, [pitcher()]) == 1  # type: ignore[arg-type]
    table, _, conflict = client.upserts[0]
    assert (table, conflict) == ("pitcher_game_stats", PITCHER_CONFLICT)


def test_team_rows_conflict_on_game_club_and_hand() -> None:
    """Two rows per club per game is normal, not a duplicate: a club that saw a
    righty starter and a lefty reliever produced against both."""
    client = _FakePostgrest()
    rows = [
        TeamBattingGameRow(
            game_pk="1", game_date=date(2026, 8, 30), batting_team="BOS",
            opp_hand=hand, plate_appearances=20, xwoba_sum=6.0,
        )
        for hand in ("L", "R")
    ]
    assert upsert_team_batting_game_stats(client, rows) == 2  # type: ignore[arg-type]
    table, sent, conflict = client.upserts[0]
    assert (table, conflict) == ("team_batting_game_stats", TEAM_CONFLICT)
    assert len(sent) == 2


# -- chunking -------------------------------------------------------------


def test_a_large_backfill_is_split_across_requests() -> None:
    """A season is ~20,000 rows and ~6.3 MB of JSON — past what Supabase will
    take in one POST, and the failure would land mid-backfill."""
    from sbm.store.game_stats import CHUNK_SIZE

    client = _FakePostgrest()
    rows = [pitcher(game_pk=str(i)) for i in range(CHUNK_SIZE * 2 + 5)]
    assert upsert_pitcher_game_stats(client, rows) == len(rows)  # type: ignore[arg-type]
    assert len(client.upserts) == 3
    assert [len(sent) for _, sent, _ in client.upserts] == [CHUNK_SIZE, CHUNK_SIZE, 5]


def test_a_nightly_batch_is_a_single_request() -> None:
    """Chunking must not add a round trip to the common path."""
    client = _FakePostgrest()
    upsert_pitcher_game_stats(client, [pitcher()])  # type: ignore[arg-type]
    assert len(client.upserts) == 1


def test_no_rows_sends_nothing() -> None:
    client = _FakePostgrest()
    assert upsert_pitcher_game_stats(client, []) == 0  # type: ignore[arg-type]
    assert client.upserts == []
