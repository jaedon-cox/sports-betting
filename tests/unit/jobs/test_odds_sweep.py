"""One priced snapshot: what gets flagged closing, and when a sweep is a failure."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from sbm.jobs import odds_sweep
from sbm.jobs.odds_sweep import (
    CREDITS_PER_SWEEP,
    SlateIntegrityError,
    SweepResult,
    assert_slate_integrity,
    sweep,
)
from sbm.jobs.slate_ingest import Slate
from sbm.odds.budget import OddsBudget
from sbm.odds.budget_store import InMemoryUsageStore
from sbm.odds.resolution import DOUBLEHEADER, NOT_INGESTED, OFF_SLATE
from sbm.sports.mlb.ingest.statsapi.schedule import ProbablePitcher, ScheduledGame
from tests.unit.jobs.fakes import FakeClient

NOW = datetime(2026, 7, 1, 22, 45, tzinfo=UTC)
NO_PITCHER = ProbablePitcher(None, None)


def game(pk: int, home: str, away: str, start_hour: int = 23) -> ScheduledGame:
    return ScheduledGame(
        game_pk=pk,
        game_date=date(2026, 7, 1),
        start_time_utc=datetime(2026, 7, 1, start_hour, 5, tzinfo=UTC),
        status="scheduled",
        home_team_id=1, home_team_name=home,
        away_team_id=2, away_team_name=away,
        venue_id=7, venue_name="Park",
        home_probable_pitcher=NO_PITCHER, away_probable_pitcher=NO_PITCHER,
        home_score=None, away_score=None,
    )


def payload(home: str, away: str) -> dict:
    return {
        "id": f"{home}-{away}",
        "home_team": home,
        "away_team": away,
        "commence_time": "2026-07-01T23:05:00Z",
        "bookmakers": [
            {
                "key": "pinnacle",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": home, "price": -120},
                            {"name": away, "price": 100},
                        ],
                    }
                ],
            }
        ],
    }


def make_slate(games: list[ScheduledGame]) -> Slate:
    return Slate(
        slate_date=date(2026, 7, 1),
        games=games,
        game_ids={str(g.game_pk): 100 + g.game_pk for g in games},
        team_ids={1: 11, 2: 22},
    )


def run_sweep(monkeypatch, games, responses, closing=frozenset()) -> tuple[FakeClient, SweepResult]:
    monkeypatch.setattr(odds_sweep, "fetch_odds", lambda **kwargs: responses)
    client = FakeClient()
    result = sweep(
        client,  # type: ignore[arg-type]
        budget=OddsBudget(store=InMemoryUsageStore()),
        api_key="key",
        slate=make_slate(games),
        sport="mlb",
        now=NOW,
        closing_external_ids=closing,
        endpoint_label="odds/mlb/close",
    )
    return client, result


def test_only_the_games_in_their_window_are_flagged_closing(monkeypatch) -> None:
    """`normalize_snapshot` takes one flag per payload, and `is_closing` is what
    `pick_settlements.closing_prob` is read by — a sweep aimed at the 7pm cluster
    must not stamp the 10pm games as closed."""
    games = [game(1, "Yankees", "Red Sox"), game(2, "Dodgers", "Giants", start_hour=1)]
    client, result = run_sweep(
        monkeypatch,
        games,
        [payload("Yankees", "Red Sox"), payload("Dodgers", "Giants")],
        closing=frozenset({"1"}),
    )
    rows = client.rows_for("line_snapshots")
    assert {row["game_id"] for row in rows if row["is_closing"]} == {101}
    assert {row["game_id"] for row in rows if not row["is_closing"]} == {102}
    assert result.closing_rows == 2  # both sides of the one closing game


def test_an_open_sweep_flags_nothing_closing(monkeypatch) -> None:
    client, _ = run_sweep(monkeypatch, [game(1, "Yankees", "Red Sox")], [payload("Yankees", "Red Sox")])
    assert all(row["is_closing"] is False for row in client.rows_for("line_snapshots"))


def test_the_raw_payload_is_archived_before_normalization(monkeypatch) -> None:
    """`fetch_odds` has no capture= seam (it would create a package cycle), so
    this is the one place holding both the bytes and a client."""
    client, _ = run_sweep(monkeypatch, [game(1, "Yankees", "Red Sox")], [payload("Yankees", "Red Sox")])
    raw = client.rows_for("raw_snapshots")
    assert len(raw) == 1
    assert raw[0]["source"] == "the_odds_api"
    assert len(raw[0]["payload"]["games"]) == 1  # a JSON array wrapped into an object


def test_rows_carry_sport_for_the_sport_markets_foreign_key(monkeypatch) -> None:
    client, _ = run_sweep(monkeypatch, [game(1, "Yankees", "Red Sox")], [payload("Yankees", "Red Sox")])
    assert all(row["sport"] == "mlb" for row in client.rows_for("line_snapshots"))
    assert all(row["devig_method"] == "power" for row in client.rows_for("line_snapshots"))


def test_routine_skips_never_trip_the_alert() -> None:
    """Doubleheaders and off-slate games are ordinary Tuesdays — an alert keyed
    on "skipped > 0" would fire nightly and be muted within a week."""
    result = SweepResult(0, 0, {DOUBLEHEADER: 2, OFF_SLATE: 11}, CREDITS_PER_SWEEP)
    assert result.alerting_skips == 0
    assert_slate_integrity(result)


def test_not_ingested_is_the_one_reason_that_fails_the_run() -> None:
    result = SweepResult(0, 0, {OFF_SLATE: 11, NOT_INGESTED: 1}, CREDITS_PER_SWEEP)
    with pytest.raises(SlateIntegrityError, match="no `games` row"):
        assert_slate_integrity(result)


def test_an_off_slate_game_is_skipped_not_priced(monkeypatch) -> None:
    """`fetch_odds` sends no date param, so tomorrow's games arrive by
    construction against a one-day-schedule resolver."""
    client, result = run_sweep(
        monkeypatch, [game(1, "Yankees", "Red Sox")],
        [payload("Yankees", "Red Sox"), payload("Cubs", "Cardinals")],
    )
    assert result.skipped_by_reason == {OFF_SLATE: 1}
    assert len(client.rows_for("line_snapshots")) == 2
