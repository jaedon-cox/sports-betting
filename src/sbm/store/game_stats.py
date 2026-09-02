"""Writers for the two per-game Statcast fact tables (db/migrations/017).

Deliberately free of pandas and numpy. `tests/unit/jobs/test_dependency_profile
.py` fails the build if Jobs B or H transitively import the scientific stack,
and both reach `sbm.store` — so the DataFrame these rows are derived from is
converted in the *job*, never here. That split is the whole reason this module
takes plain dataclasses rather than a frame.

Upsert rather than insert, which is the one place these differ from every other
fact writer in this package. `results` and `pick_settlements` are insert-once
with a reject-mutation trigger because a restated score or a re-graded pick is
a correctness failure. A re-pulled game is not: Statcast revises a game for a
day or two after it is played, and the nightly job deliberately re-covers a
trailing window so those revisions land.

`PostgrestClient.upsert` sends `resolution=merge-duplicates`, i.e. ON CONFLICT
DO UPDATE, so a re-pull *overwrites* the earlier row. That is the intent and
not merely tolerated — a revised game should end up with the revised numbers,
and DO NOTHING would pin whichever version happened to be pulled first. It is
also what makes an overlapping backfill safe to re-run.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from sbm.store.client import PostgrestClient

PITCHER_TABLE = "pitcher_game_stats"
PITCHER_CONFLICT = "player_id,game_pk"

TEAM_TABLE = "team_batting_game_stats"
TEAM_CONFLICT = "game_pk,batting_team,opp_hand"

_HANDS = ("L", "R")

CHUNK_SIZE = 1000
"""Rows per PostgREST request.

Not premature caution — a season backfill is ~20,000 pitcher-game rows at ~314
bytes of JSON each, i.e. **6.3 MB in one POST**, measured. That is past what
Supabase will accept and past a comfortable statement timeout, and the failure
would land in the middle of a long backfill rather than at its start.

1,000 rows is ~314 KB per request, which is unremarkable. The nightly run sends
a few hundred rows and never chunks at all.

**Chunking means a backfill is no longer atomic.** An interrupted run leaves
the chunks it already wrote. That is safe here and nowhere else in this
package: these are immutable per-game facts written with merge-duplicates, so
re-running covers the gap and rewrites what landed with identical values.
`picks` could never be written this way — that is what `fn_publish_run` and its
single transaction exist for."""


def _chunked(rows: list, size: int = CHUNK_SIZE):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


@dataclass(frozen=True, slots=True)
class PitcherGameRow:
    """One (pitcher, game) line of counting stats.

    No rates. `features/` weights these across games with an EWMA and a
    weighted rate has to be re-derived from separately weighted numerator and
    denominator (model doc §4.6) — a `k_pct` stored here would make the season
    figure a mean of means.
    """

    player_id: str
    game_pk: str
    game_date: date
    pitching_team: str
    throws: str | None
    is_start: bool
    pitches: int
    csw: int
    batters_faced: int
    outs: int
    strikeouts: int
    walks: int
    hit_by_pitch: int
    home_runs: int
    ground_balls: int
    fly_balls: int
    line_drives: int
    popups: int
    siera: float | None = None
    """NULL for every row this pipeline writes — SIERA is a FanGraphs formula
    and FanGraphs answers 403. Present so populating it later is a backfill,
    not a migration. See `ingest/statcast_games.py::DEFERRED`."""

    def __post_init__(self) -> None:
        """Mirror 017's `CHECK (throws IN ('L','R'))` locally, the way
        LineSnapshotRow mirrors 004's pairing: a bad value fails here naming the
        field, rather than as a PostgREST 400 partway through a batch of
        several thousand rows where nothing says which one was wrong."""
        if self.throws is not None and self.throws not in _HANDS:
            raise ValueError(f"throws must be one of {_HANDS} or None, got {self.throws!r}")


@dataclass(frozen=True, slots=True)
class TeamBattingGameRow:
    """One (game, batting club, opposing hand) line.

    Two rows per club per game is normal, not a duplicate: a club that sees a
    right-handed starter and a left-handed reliever produced against both.
    """

    game_pk: str
    game_date: date
    batting_team: str
    opp_hand: str
    plate_appearances: int
    xwoba_sum: float

    def __post_init__(self) -> None:
        if self.opp_hand not in _HANDS:
            raise ValueError(f"opp_hand must be one of {_HANDS}, got {self.opp_hand!r}")


def _row(dc: Any) -> dict[str, Any]:
    """dataclass -> JSON-safe dict; `date` is not JSON-serialisable."""
    out = asdict(dc)
    for key, value in out.items():
        if isinstance(value, date):
            out[key] = value.isoformat()
    return out


def upsert_pitcher_game_stats(
    client: PostgrestClient, rows: list[PitcherGameRow]
) -> int:
    """Write (pitcher, game) rows, ignoring ones already recorded. Returns the
    count sent, not the count inserted — PostgREST reports the representation
    of the whole batch, and distinguishing new from re-seen would cost a read
    the nightly job has no use for."""
    for batch in _chunked([_row(r) for r in rows]):
        client.upsert(PITCHER_TABLE, batch, on_conflict=PITCHER_CONFLICT)
    return len(rows)


def upsert_team_batting_game_stats(
    client: PostgrestClient, rows: list[TeamBattingGameRow]
) -> int:
    """Write (game, club, opposing hand) rows. Same conflict semantics."""
    for batch in _chunked([_row(r) for r in rows]):
        client.upsert(TEAM_TABLE, batch, on_conflict=TEAM_CONFLICT)
    return len(rows)
