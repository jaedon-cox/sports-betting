"""The Odds API client — Pinnacle only, the CLV anchor book (model doc §7).

Region is `eu` by default. Backend doc §7 item 4 (Critic finding #4, planning
doc §6): Pinnacle is *believed* to be reachable under The Odds API's `eu`
region grouping rather than `us` — this is flagged **[OPEN — verify before
build]** in the source doc, unconfirmed against a live key as of writing (see
message to `main`). Getting the region wrong doesn't error, it silently
returns a different book's line or an empty bookmakers list, which corrupts
every CLV number downstream — hence `_assert_pinnacle_present` below: any
non-empty bookmakers list that omits Pinnacle is a hard failure, never a
silent fallback to another book.

Every call must be pre-charged through `odds.budget.OddsBudget` — this module
does not know how many credits it has left, it only reports what it spent.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from sbm.odds.budget import OddsBudget

BASE_URL = "https://api.the-odds-api.com/v4"
SPORT_KEY = "baseball_mlb"
MARKETS = ("h2h", "totals", "spreads")
"""moneyline, run total, run-line — the three markets doc A2 prices (§10.2-10.4)."""

REGION = "eu"
"""Believed-correct region for Pinnacle (doc §7 item 4) — verify against a live key."""

BOOKMAKER = "pinnacle"


class PinnacleAbsentError(RuntimeError):
    """A response's bookmakers list is non-empty but omits Pinnacle.

    This almost certainly means the `regions` param is wrong, not that
    Pinnacle simply has no line yet (that case is an empty list, not a list
    missing pinnacle) — never silently substitute another book's price.
    """


def fetch_odds(
    *,
    api_key: str,
    budget: OddsBudget,
    client: httpx.Client | None = None,
    region: str = REGION,
    markets: tuple[str, ...] = MARKETS,
    endpoint_label: str = "odds/mlb",
) -> list[dict]:
    """One slate-wide snapshot call. Costs `len(markets) * 1 region` credits.

    Returns the raw JSON payload (list of per-game dicts, each with a
    `bookmakers` list) exactly as The Odds API sends it. Callers must archive
    this into `raw_snapshots` before any normalization — this function does
    not persist anything itself (ingest task 6; normalization is
    `odds/snapshot/`'s job).
    """
    budget.charge(
        markets=len(markets),
        regions=1,
        endpoint=endpoint_label,
        at=datetime.now(UTC),
    )
    owns_client = client is None
    http = client or httpx.Client(timeout=10.0)
    try:
        resp = http.get(
            f"{BASE_URL}/sports/{SPORT_KEY}/odds",
            params={
                "apiKey": api_key,
                "regions": region,
                "markets": ",".join(markets),
                "bookmakers": BOOKMAKER,
                "oddsFormat": "american",
                "dateFormat": "iso",
            },
        )
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if owns_client:
            http.close()

    _assert_pinnacle_present(payload)
    return payload


def _assert_pinnacle_present(payload: list[dict]) -> None:
    for game in payload:
        books = game.get("bookmakers") or []
        if not books:
            continue  # no line posted yet for this game — not a region error
        keys = {b.get("key") for b in books}
        if BOOKMAKER not in keys:
            raise PinnacleAbsentError(
                f"game {game.get('id')!r} returned bookmakers {sorted(keys)!r}, "
                f"no '{BOOKMAKER}' — check the `regions` param (doc §7 item 4), "
                "do not fall back to another book"
            )
