"""What the source must be *told* about tonight, versus what it reads.

`SnapshotSource`'s protocol takes only `(game_ids, as_of)`, which is right —
a feature builder should not know what a slate is. But four facts about a game
about to be played exist nowhere in the database at pick time:

* which clubs are playing and which is home,
* who each side's probable starter is (StatsAPI publishes it; it is not a
  historical fact and it changes up to first pitch),
* the internal `games.id`, since `weather_snapshots` is keyed on the surrogate
  while everything crossing into `features/` uses the gamePk (CLAUDE.md's
  cross-layer id rule),
* the venue's structural facts, which come from a StatsAPI call the job has
  already made for the weather pull.

So the job assembles these and hands them over at construction. Everything
*historical* — form, injuries, forecasts — the source reads for itself, at the
`as_of` it is given. That split is deliberate: it keeps the leakage-sensitive
half behind the as-of cut, and leaves the merely-current half to the caller
that already has it.
"""

from __future__ import annotations

from dataclasses import dataclass

from sbm.sports.mlb.ingest.statsapi.schedule import ScheduledGame
from sbm.sports.mlb.ingest.statsapi.venue import VenueInfo

SCHEDULED_INNINGS = 9.0
"""Regulation length, the denominator for `features/tto.py`'s bullpen-exposure
term. A constant rather than a read: extra innings are unknowable at pick time
and a seven-inning doubleheader game has not existed in MLB since the 2022
rule lapsed. If a shortened format returns this becomes a per-game fact."""


@dataclass(frozen=True, slots=True)
class GameContext:
    """One scheduled game, as the feature source needs it."""

    external_id: str
    """gamePk as a string — the id that crosses into `features/`."""
    internal_id: int
    """`games.id`, needed only to read `weather_snapshots`."""
    home_team: str
    away_team: str
    """Club codes. Verified identical between StatsAPI and Statcast, so these
    key `pitcher_game_stats.pitching_team` directly (db/migrations/017)."""
    home_team_id: int | None
    away_team_id: int | None
    """`teams.id`, for the injury read."""
    home_starter_id: str | None
    away_starter_id: str | None
    """MLBAM ids. None when no probable is published yet — routine hours before
    first pitch, and the reason `pitcher_inputs` must degrade to NaN rather
    than raise: a slate is priced with whatever is known at `as_of`."""
    venue: VenueInfo | None


def build_context(
    game: ScheduledGame,
    *,
    internal_id: int,
    home_code: str,
    away_code: str,
    venue: VenueInfo | None,
) -> GameContext:
    """`ScheduledGame` -> `GameContext`, resolving the probable starters.

    Team *codes* are passed in rather than read off `ScheduledGame`, which
    carries only StatsAPI's numeric team id and full name — the code lives in
    `teams`, which the job has already upserted.
    """
    return GameContext(
        external_id=str(game.game_pk),
        internal_id=internal_id,
        home_team=home_code,
        away_team=away_code,
        home_team_id=game.home_team_id,
        away_team_id=game.away_team_id,
        home_starter_id=_probable(game, "home"),
        away_starter_id=_probable(game, "away"),
        venue=venue,
    )


def _probable(game: ScheduledGame, side: str) -> str | None:
    """The listed starter's MLBAM id, as TEXT to match `pitcher_game_stats`.

    Str rather than int for the same reason the column is TEXT: it has to join
    against `injury_snapshots.player_id`, which is TEXT because ids are not
    numeric in every sport (CLAUDE.md rule 7).
    """
    probable = getattr(game, f"{side}_probable_pitcher", None)
    player_id = getattr(probable, "player_id", None) if probable else None
    return None if player_id is None else str(player_id)
