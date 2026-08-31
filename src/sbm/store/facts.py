"""Mutable fact/reference writers `ingest` needs alongside the snapshot
tables: teams and games (both upsert, neither is append-only) and
results (insert-once at final, §3.2). No business logic — callers decide
what row to write; this module only picks the right client call and
on_conflict key.
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
    raises a unique-violation instead of silently overwriting a score."""
    return client.insert("results", [asdict(r) for r in results])
