"""Team reference data + the Odds-API-team-name -> game_id resolvers.

The Odds API's payload carries `home_team`/`away_team` as free-text names
("New York Yankees"), not MLB's numeric team id or `gamePk` — matching an
odds snapshot to our own schedule is a (team-name pair) join. This module
builds that join from one day's `fetch_schedule` output, so odds
normalization never has to know StatsAPI's shapes and doesn't need its own
network call.

**Two resolvers, deliberately different return types.** `odds/snapshot/`
writes `line_snapshots.game_id`, which is `db`'s *internal* `games.id`
(an int PostgREST assigns), not the external StatsAPI `gamePk`. Schedule
data alone can only produce the latter. So:

- `build_external_game_id_resolver` -> `gamePk`. Everything schedule data
  can answer on its own.
- `compose_internal_resolver` maps that through an external-id -> internal-id
  mapping (e.g. `db.upsert_games()`'s returned rows) to get the resolver
  `normalize_snapshot` actually requires.

Passing the external resolver straight into `normalize_snapshot` is a type
error rather than a silent wrong-key bug — which is the whole point of not
collapsing these two into one resolver name.

**Neither returns `Optional`.** Both return `odds/resolution.py`'s
`Resolved…`/`Unresolved` pair, so a failed lookup carries *why* it failed and
cannot flow into a query filter as a `None` (`core`'s audit finding). The
three failure reasons are genuinely different operationally — see that
module — and this is the layer that knows which one applies: an ambiguous
team pair is a doubleheader, a missing one is off-slate, and a gamePk absent
from the id mapping is a game not yet ingested.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from sbm.odds.resolution import (
    DOUBLEHEADER,
    NOT_INGESTED,
    OFF_SLATE,
    ExternalGameIdResolver,
    ExternalResolution,
    GameIdResolution,
    GameIdResolver,
    ResolvedExternalId,
    ResolvedGameId,
    Unresolved,
)
from sbm.sports.mlb.ingest.statsapi.schedule import ScheduledGame


def build_external_game_id_resolver(games: list[ScheduledGame]) -> ExternalGameIdResolver:
    """Matches on (home team full name, away team full name).

    A doubleheader's two games share a team pair for the same date — that
    collision is reported as `DOUBLEHEADER` rather than guessing the first
    match, which would charge a line to the wrong half of the twin bill.
    A pair absent from the slate entirely is `OFF_SLATE`: the odds feed
    spans a wider window than the one date this index covers.
    """
    index = _index(games)

    def resolve(home_team: str, away_team: str, commence_time: datetime) -> ExternalResolution:
        del commence_time  # `games` is already scoped to one officialDate
        key = (home_team, away_team)
        if key not in index:
            return Unresolved(OFF_SLATE, home_team, away_team)
        external_id = index[key]
        if external_id is None:
            return Unresolved(DOUBLEHEADER, home_team, away_team)
        return ResolvedExternalId(external_id)

    return resolve


def compose_internal_resolver(
    external: ExternalGameIdResolver,
    external_to_internal: Mapping[str, int],
) -> GameIdResolver:
    """Lift an external (`gamePk`) resolver into an internal (`games.id`) one.

    An unmapped `gamePk` is `NOT_INGESTED` rather than a raise: a game the
    odds feed knows about but `games` hasn't been upserted with yet is an
    ordinary within-run ordering gap. It is still the reason worth alerting
    on if it dominates a slate, which is why it stays distinguishable from
    the other two rather than collapsing into a shared "unresolved".
    """

    def resolve(home_team: str, away_team: str, commence_time: datetime) -> GameIdResolution:
        resolution = external(home_team, away_team, commence_time)
        if not isinstance(resolution, ResolvedExternalId):
            return resolution
        internal = external_to_internal.get(resolution.external_id)
        if internal is None:
            return Unresolved(NOT_INGESTED, home_team, away_team)
        return ResolvedGameId(internal)

    return resolve


def _index(games: list[ScheduledGame]) -> dict[tuple[str, str], str | None]:
    counts: dict[tuple[str, str], int] = {}
    first: dict[tuple[str, str], str] = {}
    for game in games:
        if game.home_team_name is None or game.away_team_name is None:
            continue
        key = (game.home_team_name, game.away_team_name)
        counts[key] = counts.get(key, 0) + 1
        first.setdefault(key, str(game.game_pk))
    return {key: (first[key] if counts[key] == 1 else None) for key in counts}
