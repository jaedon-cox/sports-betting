"""Offline tests via httpx.MockTransport — no real network (see CLAUDE.md conventions)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from sbm.odds.budget import BudgetExceeded, OddsBudget
from sbm.odds.budget_store import InMemoryUsageStore
from sbm.odds.theoddsapi import PinnacleAbsentError, fetch_odds

GAME_WITH_PINNACLE = {
    "id": "abc123",
    "sport_key": "baseball_mlb",
    "commence_time": "2026-08-29T23:05:00Z",
    "home_team": "New York Yankees",
    "away_team": "Boston Red Sox",
    "bookmakers": [
        {
            "key": "pinnacle",
            "title": "Pinnacle",
            "last_update": "2026-08-29T20:00:00Z",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "New York Yankees", "price": -150},
                        {"name": "Boston Red Sox", "price": 130},
                    ],
                }
            ],
        }
    ],
}

GAME_WITHOUT_PINNACLE = {
    "id": "def456",
    "bookmakers": [{"key": "draftkings", "title": "DraftKings", "markets": []}],
}

GAME_WITH_NO_LINE_YET = {"id": "ghi789", "bookmakers": []}


def _client(payload: list[dict], *, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _budget(cap: int = 500) -> OddsBudget:
    return OddsBudget(store=InMemoryUsageStore(), cap=cap)


def test_fetch_odds_returns_payload_and_charges_budget() -> None:
    budget = _budget()
    payload = fetch_odds(
        api_key="test-key",
        budget=budget,
        client=_client([GAME_WITH_PINNACLE]),
    )
    assert payload == [GAME_WITH_PINNACLE]
    # 3 markets x 1 region = 3 credits (doc §2.5).
    assert budget.remaining(at=datetime.now(UTC)) == 497


def test_fetch_odds_refuses_when_budget_exhausted() -> None:
    budget = _budget(cap=2)
    with pytest.raises(BudgetExceeded):
        fetch_odds(api_key="test-key", budget=budget, client=_client([GAME_WITH_PINNACLE]))


def test_fetch_odds_fails_loud_when_pinnacle_absent_but_other_books_present() -> None:
    budget = _budget()
    with pytest.raises(PinnacleAbsentError):
        fetch_odds(
            api_key="test-key",
            budget=budget,
            client=_client([GAME_WITHOUT_PINNACLE]),
        )


def test_fetch_odds_tolerates_a_game_with_no_line_posted_yet() -> None:
    budget = _budget()
    payload = fetch_odds(
        api_key="test-key",
        budget=budget,
        client=_client([GAME_WITH_NO_LINE_YET]),
    )
    assert payload == [GAME_WITH_NO_LINE_YET]


def test_fetch_odds_raises_on_http_error() -> None:
    budget = _budget()
    with pytest.raises(httpx.HTTPStatusError):
        fetch_odds(
            api_key="test-key",
            budget=budget,
            client=_client([], status=401),
        )
