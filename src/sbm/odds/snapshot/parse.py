"""The only module that knows The Odds API's JSON shape.

Everything here reads the wire format defensively — `.get()` with a default,
never an index — because the payload is an external contract we don't
control. A shape change upstream should degrade one market to "skipped",
not crash the whole slate's pull. `rows.py` owns what we *write*; this owns
what we *read*, so a wire-format change lands in exactly one file.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sbm.odds.snapshot.rows import DevigFn, LineSnapshotRow, Market

BOOKMAKER = "pinnacle"

_ODDS_API_MARKET_TO_OURS: dict[str, Market] = {
    "h2h": "moneyline",
    "totals": "total",
    "spreads": "spread",
}


def pinnacle_book(game: dict) -> dict | None:
    """Pinnacle's block, or `None` if it hasn't posted this game yet.

    `None` here means pre-open, which is routine. It is NOT the same as
    `theoddsapi.PinnacleAbsentError`, which fires when *other* books are
    present but Pinnacle isn't — that means the region param is wrong.
    """
    for book in game.get("bookmakers") or []:
        if book.get("key") == BOOKMAKER:
            return book
    return None


def parse_commence(game: dict) -> datetime:
    raw = game.get("commence_time")
    if not raw:
        return datetime.min
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _side_for_team(name: str, game: dict) -> str | None:
    if name == game.get("home_team"):
        return "home"
    if name == game.get("away_team"):
        return "away"
    return None


def _side_of_team_outcome(outcome: dict, game: dict) -> str | None:
    return _side_for_team(outcome.get("name", ""), game)


def _side_of_total_outcome(outcome: dict, game: dict) -> str | None:
    del game
    name = str(outcome.get("name", "")).lower()
    return name if name in ("over", "under") else None


_SIDE_OF: dict[Market, Callable[[dict, dict], str | None]] = {
    "moneyline": _side_of_team_outcome,
    "total": _side_of_total_outcome,
    "spread": _side_of_team_outcome,
}


def market_rows(
    game_id: int,
    game: dict,
    market_block: dict,
    *,
    devig: DevigFn,
    method: str,
    captured_at_utc: datetime,
    is_closing: bool,
) -> list[LineSnapshotRow]:
    """One market block -> its two rows, or `[]` if it isn't usable.

    A partial quote (one side priced, or a market key we don't carry) yields
    nothing rather than a guess: inventing the missing side would put a
    fabricated price into an append-only table that CLV is measured against.
    """
    ours = _ODDS_API_MARKET_TO_OURS.get(market_block.get("key", ""))
    if ours is None:
        return []
    side_of = _SIDE_OF[ours]
    prices: dict[str, int] = {}
    lines: dict[str, float | None] = {}
    for outcome in market_block.get("outcomes", []):
        side = side_of(outcome, game)
        if side is None or "price" not in outcome:
            continue
        prices[side] = outcome["price"]
        lines[side] = outcome.get("point")

    if len(prices) != 2:
        return []  # malformed/partial quote — skip defensively, never guess a side

    fair = devig(prices, method=method)
    return [
        LineSnapshotRow(
            game_id=game_id,
            market=ours,
            side=side,
            line=lines[side],
            price_american=price,
            implied_prob_devigged=fair[side],
            captured_at_utc=captured_at_utc,
            is_closing=is_closing,
            devig_method=method,
        )
        for side, price in prices.items()
    ]
