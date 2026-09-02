"""Assembles the `SnapshotSource` Jobs C and D hand to the model.

`PostgrestSnapshotSource` reads everything historical for itself, but four
facts about a game about to be played exist nowhere in the database at pick
time — the clubs, the probable starters, the internal `games.id`, and the
venue's structural facts (`features/source/context.py` explains why). This
module gathers those from the slate the job already ingested.

**Venues are fetched once per venue, not per game**, and a lookup failure
degrades that game's park columns to null rather than failing the run: a
missing roof type costs one feature, and `columns.py` defaults it, whereas
raising would cost the whole slate its picks.
"""

from __future__ import annotations

from sbm.jobs.slate_ingest import Slate
from sbm.sports.mlb.features.source import GameContext, PostgrestSnapshotSource
from sbm.sports.mlb.features.source.context import build_context
from sbm.sports.mlb.ingest.statsapi import StatsApiClient, fetch_venue
from sbm.sports.mlb.ingest.statsapi.venue import VenueInfo
from sbm.store.client import PostgrestClient


def build_source(
    client: PostgrestClient, *, stats: StatsApiClient, slate: Slate, team_codes: dict[int, str]
) -> PostgrestSnapshotSource:
    """The source for one slate. `team_codes` maps StatsAPI team id -> code."""
    venues: dict[int, VenueInfo | None] = {}
    games: dict[str, GameContext] = {}
    for game in slate.games:
        external = str(game.game_pk)
        internal = slate.game_ids.get(external)
        home = team_codes.get(game.home_team_id or -1)
        away = team_codes.get(game.away_team_id or -1)
        if internal is None or home is None or away is None:
            # Not in `games`/`teams` yet — the same skip `slate_ingest._game_row`
            # makes, and for the same reason: one unkeyable game, not the slate.
            continue
        games[external] = build_context(
            game,
            internal_id=internal,
            home_code=home,
            away_code=away,
            venue=_venue(stats, game.venue_id, venues),
        )
    return PostgrestSnapshotSource(client=client, games=games)


def _venue(
    stats: StatsApiClient, venue_id: int | None, cache: dict[int, VenueInfo | None]
) -> VenueInfo | None:
    """Venue facts, memoised per venue and never fatal.

    A doubleheader is two games at one ballpark; without the memo that is two
    identical calls against a 1 req/s throttle.
    """
    if venue_id is None:
        return None
    if venue_id not in cache:
        try:
            cache[venue_id] = fetch_venue(venue_id, client=stats)
        except Exception as exc:  # noqa: BLE001 — a park fact is never worth the slate
            print(f"features: venue {venue_id} unavailable, park columns null — {exc}")
            cache[venue_id] = None
    return cache[venue_id]
