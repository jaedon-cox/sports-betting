"""One slate date's schedule -> `teams` + `games` rows, and the id maps.

Shared by every job that touches a slate, because all of them need the same
three things and none of them can derive them alone:

* the day's `ScheduledGame` list (start times, statuses, probables, scores),
* `external_game_id -> games.id`, since `line_snapshots.game_id` and
  `picks.game_id` are the Postgres surrogate while everything crossing into
  `features/` uses the gamePk (CLAUDE.md's cross-layer id rule),
* `GameIdResolver`, which `odds/snapshot.normalize_snapshot` requires and which
  only exists once both of the above do.

The mapping comes out of `upsert_games`' own returned representation rather
than a separate read: the upsert is idempotent and already round-trips the
rows, so asking for the ids again would be a second request for data we were
just handed.

Schedule payloads are archived through `capture=` (backend doc §2.1) — probable
pitchers get scratched, so which starter was *listed at pull time* is a
point-in-time fact the parse throws away.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sbm.jobs.mlb_reference import fetch_team_rows
from sbm.odds.resolution import GameIdResolver
from sbm.sports.mlb.ingest.archive import CaptureList
from sbm.sports.mlb.ingest.statsapi import (
    ScheduledGame,
    StatsApiClient,
    build_external_game_id_resolver,
    compose_internal_resolver,
    fetch_schedule,
)
from sbm.store.client import PostgrestClient
from sbm.store.facts import GameRow, upsert_games, upsert_teams


@dataclass(frozen=True, slots=True)
class Slate:
    """One ET slate date, as the rest of the pipeline needs it."""

    slate_date: date
    games: list[ScheduledGame]
    game_ids: dict[str, int]
    """external_game_id (gamePk, str) -> games.id (int)."""
    team_ids: dict[int, int]
    """StatsAPI team id -> teams.id (int)."""

    @property
    def external_ids(self) -> list[str]:
        """The ids that cross into `features/` — gamePks, in schedule order."""
        return [str(game.game_pk) for game in self.games]

    def resolver(self) -> GameIdResolver:
        """(home name, away name, commence) -> `games.id`, for odds normalization."""
        return compose_internal_resolver(
            build_external_game_id_resolver(self.games), self.game_ids
        )


def ingest_slate(
    client: PostgrestClient,
    *,
    stats: StatsApiClient,
    sport: str,
    slate_date: date,
    capture: CaptureList | None = None,
) -> Slate:
    """Pull the schedule, upsert teams and games, return the maps.

    `games` is ordinary mutable reference state, not append-only (backend doc
    §3.1), so calling this repeatedly through the day is the intended pattern —
    it is how a game's status walks scheduled -> in_progress -> final.
    """
    games = fetch_schedule(slate_date, client=stats, capture=capture)
    team_rows = fetch_team_rows(client=stats)
    stored_teams = upsert_teams(client, list(team_rows.values()))
    code_to_id = {str(row["code"]): int(row["id"]) for row in stored_teams}
    team_ids = {
        statsapi_id: code_to_id[row.code]
        for statsapi_id, row in team_rows.items()
        if row.code in code_to_id
    }

    rows = [_game_row(game, sport, team_ids) for game in games]
    stored_games = upsert_games(client, [row for row in rows if row is not None])
    game_ids = {str(row["external_game_id"]): int(row["id"]) for row in stored_games}
    return Slate(slate_date=slate_date, games=games, game_ids=game_ids, team_ids=team_ids)


def _game_row(game: ScheduledGame, sport: str, team_ids: dict[int, int]) -> GameRow | None:
    """None for a game we cannot key — an unknown team id or no official date.

    Skipping one malformed game is right; letting it raise would drop the whole
    slate over a single upstream shape change, which is the failure mode every
    parse in `ingest` is written to avoid.
    """
    home = team_ids.get(game.home_team_id or -1)
    away = team_ids.get(game.away_team_id or -1)
    if home is None or away is None or game.game_date is None:
        return None
    return GameRow(
        sport=sport,
        external_game_id=str(game.game_pk),
        game_date=game.game_date.isoformat(),
        home_team_id=home,
        away_team_id=away,
        start_time_utc=game.start_time_utc.isoformat() if game.start_time_utc else None,
        park_name=game.venue_name,
        status=game.status,
    )
