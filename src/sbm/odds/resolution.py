"""Game-id resolution outcomes — the vocabulary that keeps `None` out of a
query filter.

Resolution used to return `int | None`, and `core`'s audit was right that an
`Optional` flowing onward is how a join silently returns nothing. But an
unconditional raise is wrong too, because **an unresolvable game is routine
here, not a corruption**, for three genuinely different reasons that a bare
`None` (or a bare raise) flattens into one:

- `DOUBLEHEADER` — two games share a team pair on the slate date, so the
  pair cannot identify one game. `teams.py` refuses to guess rather than
  charge a line to the wrong half of a twin bill. Rain makeups make this an
  ordinary Tuesday, not an incident.
- `OFF_SLATE` — the odds feed carries games our resolver's slate date does
  not. `theoddsapi.fetch_odds` sends no date parameter (it returns The Odds
  API's whole upcoming window), while the resolver is built from one
  `officialDate`'s schedule, so tomorrow's games arrive unresolvable by
  construction.
- `NOT_INGESTED` — a real game on our slate whose `games` row doesn't exist
  yet. This is the one `core` had in mind, and the only one that indicates
  something upstream is actually wrong.

Keeping the reason is what lets a job tell "3 skipped, all doubleheaders"
(fine) from "15 skipped, all NOT_INGESTED" (schedule ingest is broken) —
a distinction neither `None` nor a raise can express, and the reason the
skip decision belongs to the caller with a count attached rather than to
the resolver with an exception.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

DOUBLEHEADER = "doubleheader"
"""Team pair is ambiguous on the slate date — deliberately not guessed."""

OFF_SLATE = "off_slate"
"""Team pair isn't on the resolver's slate date at all."""

NOT_INGESTED = "not_ingested"
"""Resolved to a gamePk with no `games` row yet — the one that's a real signal."""

NO_PINNACLE_BOOK = "no_pinnacle_book"
"""Pinnacle hasn't posted a line for this game yet (pre-open, not an error).

Distinct from `theoddsapi.PinnacleAbsentError`, which fires when *other* books
are present but Pinnacle isn't — that means the region param is wrong.
"""


@dataclass(frozen=True, slots=True)
class ResolvedGameId:
    """`db`'s internal `games.id` — what `line_snapshots.game_id` stores."""

    game_id: int


@dataclass(frozen=True, slots=True)
class ResolvedExternalId:
    """StatsAPI `gamePk`, as a string. Not a storage surrogate; the id the
    sport itself uses, which is what crosses into `sports/*/features/`."""

    external_id: str


@dataclass(frozen=True, slots=True)
class Unresolved:
    """Why one game produced no id. Carries the teams so a log line is
    actionable without re-deriving them from the payload."""

    reason: str
    home_team: str
    away_team: str


GameIdResolution = ResolvedGameId | Unresolved
ExternalResolution = ResolvedExternalId | Unresolved

GameIdResolver = Callable[[str, str, datetime], GameIdResolution]
"""(home_team, away_team, commence_time) -> `db`'s internal `games.id`.

NOT the external StatsAPI `gamePk` — `sbm.store.snapshots.LineSnapshotRow.game_id`
is the `int` PostgREST assigns, which this layer cannot know on its own.
`statsapi.teams.build_external_game_id_resolver` gives the gamePk from
schedule data alone; compose it with an external-id -> internal-id mapping
(e.g. `db.upsert_games()`'s return value) via
`statsapi.teams.compose_internal_resolver`. Passing the external resolver
here directly is a type error, not a silent bug, by design.
"""

ExternalGameIdResolver = Callable[[str, str, datetime], ExternalResolution]
"""Same inputs -> StatsAPI `gamePk`. Feeds `compose_internal_resolver`."""
