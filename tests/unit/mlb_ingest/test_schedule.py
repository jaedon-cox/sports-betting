"""Offline tests via httpx.MockTransport — no real network."""

from __future__ import annotations

from datetime import date

import httpx

from sbm.sports.mlb.ingest.statsapi.client import StatsApiClient
from sbm.sports.mlb.ingest.statsapi.schedule import extract_final_results, fetch_schedule

SCHEDULE_PAYLOAD = {
    "dates": [
        {
            "games": [
                {
                    "gamePk": 823452,
                    "gameDate": "2026-06-15T22:40:00Z",
                    "officialDate": "2026-06-15",
                    "status": {
                        "abstractGameState": "Final",
                        "codedGameState": "F",
                        "detailedState": "Final",
                    },
                    "venue": {"id": 2681, "name": "Citizens Bank Park"},
                    "teams": {
                        "away": {
                            "team": {"id": 146, "name": "Miami Marlins"},
                            "score": 2,
                            "probablePitcher": {"id": 687473, "fullName": "Ryan Gusto"},
                        },
                        "home": {
                            "team": {"id": 143, "name": "Philadelphia Phillies"},
                            "score": 5,
                            "probablePitcher": {"id": 605400, "fullName": "Aaron Nola"},
                        },
                    },
                },
                {
                    # Postponed game: no probable pitcher, no score.
                    "gamePk": 999999,
                    "gameDate": "2026-06-15T18:00:00Z",
                    "officialDate": "2026-06-15",
                    "status": {"abstractGameState": "Preview", "detailedState": "Postponed"},
                    "teams": {
                        "away": {"team": {"id": 111, "name": "Boston Red Sox"}},
                        "home": {"team": {"id": 147, "name": "New York Yankees"}},
                    },
                },
                {
                    # Missing gamePk entirely — must be skipped, not crash the pull.
                    "officialDate": "2026-06-15",
                    "status": {},
                    "teams": {},
                },
            ]
        }
    ]
}


def _client(payload: dict) -> StatsApiClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return StatsApiClient(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_schedule_parses_a_final_game_fully() -> None:
    games = fetch_schedule(date(2026, 6, 15), client=_client(SCHEDULE_PAYLOAD))
    final = next(g for g in games if g.game_pk == 823452)
    assert final.status == "final"
    assert final.home_team_id == 143
    assert final.home_team_name == "Philadelphia Phillies"
    assert final.away_team_name == "Miami Marlins"
    assert final.home_score == 5
    assert final.away_score == 2
    assert final.home_probable_pitcher.full_name == "Aaron Nola"
    assert final.venue_name == "Citizens Bank Park"
    assert final.game_date == date(2026, 6, 15)


def test_fetch_schedule_normalizes_postponed_via_detailed_state() -> None:
    games = fetch_schedule(date(2026, 6, 15), client=_client(SCHEDULE_PAYLOAD))
    postponed = next(g for g in games if g.game_pk == 999999)
    assert postponed.status == "postponed"
    assert postponed.home_probable_pitcher.player_id is None


def test_fetch_schedule_skips_games_with_no_game_pk() -> None:
    games = fetch_schedule(date(2026, 6, 15), client=_client(SCHEDULE_PAYLOAD))
    assert len(games) == 2  # the malformed third game is dropped, not raised


def test_extract_final_results_only_returns_terminal_games_with_scores() -> None:
    games = fetch_schedule(date(2026, 6, 15), client=_client(SCHEDULE_PAYLOAD))
    results = extract_final_results(games)
    assert len(results) == 1
    assert results[0].game_pk == 823452
    assert results[0].home_runs == 5
    assert results[0].away_runs == 2
