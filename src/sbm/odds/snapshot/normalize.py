"""Orchestration and skip accounting — the package's one public entry point.

Joins `parse.py` (what the wire says) to `rows.py` (what we store), and owns
the one policy decision neither of them can make: what to do when a game
yields no rows. That is always "skip and record why", never a raise and never
a silent drop — see `odds/resolution.py` for why the reason has to survive.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sbm.core.pricing.devig import devig_sides
from sbm.odds.resolution import (
    NO_PINNACLE_BOOK,
    GameIdResolver,
    ResolvedGameId,
    Unresolved,
)
from sbm.odds.snapshot.parse import market_rows, parse_commence, pinnacle_book
from sbm.odds.snapshot.rows import DEVIG_METHOD, DevigFn, LineSnapshotRow


@dataclass(frozen=True, slots=True)
class NormalizedSnapshot:
    """Rows to insert, plus every game that produced none and why.

    `skipped` is not diagnostics padding: skipping is the correct behaviour
    for a pre-open book, a doubleheader, and an off-slate game, but the same
    silence would also be the symptom of schedule ingest having died. Both
    produce zero rows, so only the counts separate them — and the caller is
    the only layer that can, because it knows how many games it expected.
    """

    rows: list[LineSnapshotRow]
    skipped: list[Unresolved]

    @property
    def skipped_by_reason(self) -> dict[str, int]:
        """Ready to log as one line, or to threshold an alert on."""
        counts: dict[str, int] = {}
        for skip in self.skipped:
            counts[skip.reason] = counts.get(skip.reason, 0) + 1
        return counts


def normalize_snapshot(
    payload: list[dict],
    *,
    resolve_game_id: GameIdResolver,
    captured_at_utc: datetime,
    is_closing: bool,
    devig: DevigFn = devig_sides,
    method: str = DEVIG_METHOD,
) -> NormalizedSnapshot:
    """Turn one Odds API response into `line_snapshots` rows, ready to insert.

    A game with no Pinnacle book yet, or one that doesn't resolve, is skipped
    and recorded in `skipped` — not raised, and not dropped silently. Both are
    expected pre-open/join-gap states, unlike the region mismatch
    `theoddsapi.py` already fails loud on.

    This function does not persist anything and makes no network call: the
    caller archives the raw payload to `raw_snapshots` (backend doc §2.1) at
    the fetch site, where the untouched bytes still exist.
    """
    rows: list[LineSnapshotRow] = []
    skipped: list[Unresolved] = []
    for game in payload:
        home = str(game.get("home_team", ""))
        away = str(game.get("away_team", ""))
        book = pinnacle_book(game)
        if book is None:
            skipped.append(Unresolved(NO_PINNACLE_BOOK, home, away))
            continue
        resolution = resolve_game_id(home, away, parse_commence(game))
        if not isinstance(resolution, ResolvedGameId):
            skipped.append(resolution)
            continue
        for market_block in book.get("markets", []):
            rows.extend(
                market_rows(
                    resolution.game_id,
                    game,
                    market_block,
                    devig=devig,
                    method=method,
                    captured_at_utc=captured_at_utc,
                    is_closing=is_closing,
                )
            )
    return NormalizedSnapshot(rows=rows, skipped=skipped)
