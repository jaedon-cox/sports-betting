"""Fact/reference writers outside the snapshot tables: teams and games
(both upsert, neither is append-only) plus the two insert-once
settlement-time facts, results and pick_settlements (§3.2). No business
logic — callers decide what row to write; this module only picks the
right client call and on_conflict key.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sbm.store.client import PostgrestClient


@dataclass(frozen=True, slots=True)
class TeamRow:
    sport: str
    code: str
    name: str
    league: str | None = None
    division: str | None = None


@dataclass(frozen=True, slots=True)
class GameRow:
    sport: str
    external_game_id: str
    game_date: str  # ISO date
    home_team_id: int
    away_team_id: int
    start_time_utc: str | None = None  # ISO datetime
    park_name: str | None = None
    status: str = "scheduled"


@dataclass(frozen=True, slots=True)
class ResultRow:
    game_id: int
    home_score: int
    away_score: int
    final_status: str
    detail: dict[str, Any] | None = None


_OUTCOMES = ("win", "loss", "push", "void")


@dataclass(frozen=True, slots=True)
class SettlementRow:
    """One pick_settlements row (insert-once, post-game, §3.2).

    clv_pct is RELATIVE — `(closing_prob - bet_prob) / bet_prob`, straight
    from core/clv.py's compute_clv, which is the single definition of "CLV
    pct" in this system. Never the absolute v_pick_clv_live.clv_abs_live.
    """

    pick_id: int
    outcome: str
    bet_prob: float | None = None
    closing_prob: float | None = None
    clv_pct: float | None = None

    def __post_init__(self) -> None:
        """Fail earlier, and naming the field, for two constraints the
        database also enforces — 004's outcome CHECK and 016's clv_pct
        provenance CHECK. Same role as LineSnapshotRow's guard: without it
        a bad row surfaces as a PostgREST 400 partway through a settlement
        batch, which says far less about what went wrong.

        Neither state is reachable from Job F today — its _clv() returns
        None whenever a leg is missing, and outcomes come from a closed
        set. These bind the next writer, not the current one; the database
        constraints are what actually hold the line, since the
        service-role key can INSERT here without passing through this
        class at all.
        """
        if self.outcome not in _OUTCOMES:
            raise ValueError(f"outcome must be one of {_OUTCOMES}, got {self.outcome!r}")
        if self.clv_pct is not None and (self.bet_prob is None or self.closing_prob is None):
            raise ValueError(
                f"clv_pct={self.clv_pct!r} needs both the probs it was derived from "
                f"(got bet_prob={self.bet_prob!r}, closing_prob={self.closing_prob!r})"
            )


def upsert_teams(client: PostgrestClient, teams: list[TeamRow]) -> list[dict[str, Any]]:
    """Upsert on (sport, code) — teams is sport-scoped, not globally
    unique on code (main notified, forward-compat: see
    db/migrations/001_reference_and_versioning.sql)."""
    return client.upsert("teams", [asdict(t) for t in teams], on_conflict="sport,code")


def upsert_games(client: PostgrestClient, games: list[GameRow]) -> list[dict[str, Any]]:
    """Upsert on (sport, external_game_id). games is ordinary mutable
    state (schedule + status progression), not in the append-only set —
    Job A/B write here repeatedly as a game's status changes."""
    return client.upsert("games", [asdict(g) for g in games], on_conflict="sport,external_game_id")


def write_results(client: PostgrestClient, results: list[ResultRow]) -> list[dict[str, Any]]:
    """Insert-once final scores (§3.2). No upsert path exists: results
    has a reject-mutation trigger, so writing the same game_id twice
    raises a unique-violation instead of silently overwriting a score.
    Job F's nightly sweep wants the rerun-safe path instead — that is
    fn_record_results (db/migrations/014_settlement_rpcs.sql), which does
    ON CONFLICT DO NOTHING and fires no trigger."""
    return client.insert("results", [asdict(r) for r in results])


def write_settlements(client: PostgrestClient, settlements: list[SettlementRow]) -> int:
    """Insert-once settlements (§3.1); returns the number of rows written.

    Plain INSERT, no upsert path, for the same reason as write_results:
    pick_settlements carries a reject-mutation trigger, so a re-settle
    raises a primary-key violation rather than restating a graded pick.
    Job F gets its idempotency from fn_unsettled_picks keying on the
    absence of a settlement row, not from this call being repeatable.
    """
    client.insert("pick_settlements", [asdict(s) for s in settlements])
    return len(settlements)
