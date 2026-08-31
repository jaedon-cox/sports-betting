"""Daily schedule, probable pitchers, live/final scores (backend doc §2.1,
jobs A/F). One endpoint covers all three: `teams.{home,away}.score` is
populated as soon as a game goes live and stays populated at final, so no
separate "live scores" or "final results" endpoint call is needed.

Unofficial API — every field read below is defensive (`.get()` with a
default); a shape change upstream degrades one field to `None` rather than
crashing the pull for the whole slate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sbm.sports.mlb.ingest.archive import (
    ENTITY_SCHEDULE,
    SOURCE_STATSAPI,
    CaptureSink,
    capture_payload,
)
from sbm.sports.mlb.ingest.statsapi.client import StatsApiClient


@dataclass(frozen=True, slots=True)
class ProbablePitcher:
    player_id: int | None
    full_name: str | None


@dataclass(frozen=True, slots=True)
class ScheduledGame:
    """Normalized input to the `games` table (backend doc §3.2), plus score."""

    game_pk: int
    game_date: date | None
    """ET slate-date == StatsAPI's `officialDate`."""
    start_time_utc: datetime | None
    status: str
    """'scheduled' | 'in_progress' | 'final' | 'postponed' | 'cancelled'."""
    home_team_id: int | None
    home_team_name: str | None
    away_team_id: int | None
    away_team_name: str | None
    venue_id: int | None
    venue_name: str | None
    home_probable_pitcher: ProbablePitcher
    away_probable_pitcher: ProbablePitcher
    home_score: int | None
    away_score: int | None


@dataclass(frozen=True, slots=True)
class FinalResult:
    """One `results` row (backend doc §3.2) — insert-once at final."""

    game_pk: int
    home_runs: int
    away_runs: int
    final_status: str


def fetch_schedule(
    as_of_date: date,
    *,
    client: StatsApiClient,
    capture: CaptureSink | None = None,
) -> list[ScheduledGame]:
    """All MLB games for one slate-date. Job A cadence: 1x/day ~8am ET.

    Pass `capture=` to archive the untouched payload to `raw_snapshots`
    (backend doc §2.1) — probable pitchers get scratched, so which starter
    was listed *at pull time* is a point-in-time fact this parse would
    otherwise throw away. See `ingest/archive.py`.
    """
    payload = client.get(
        "/schedule",
        params={
            "sportId": 1,
            "date": as_of_date.isoformat(),
            "hydrate": "probablePitcher,team,venue",
        },
    )
    capture_payload(
        capture,
        payload,
        source=SOURCE_STATSAPI,
        entity_type=ENTITY_SCHEDULE,
        entity_id=as_of_date.isoformat(),
    )
    games = []
    for day in payload.get("dates", []):
        for raw in day.get("games", []):
            game = _parse_game(raw)
            if game is not None:
                games.append(game)
    return games


def extract_final_results(games: list[ScheduledGame]) -> list[FinalResult]:
    """Terminal-state games ready for `results` (job F) — no extra HTTP call."""
    out = []
    for g in games:
        if g.status != "final" or g.home_score is None or g.away_score is None:
            continue
        out.append(
            FinalResult(
                game_pk=g.game_pk, home_runs=g.home_score, away_runs=g.away_score, final_status=g.status
            )
        )
    return out


def _parse_game(raw: dict) -> ScheduledGame | None:
    game_pk = raw.get("gamePk")
    if game_pk is None:
        return None  # can't identify the game — skip, don't crash the whole slate
    teams = raw.get("teams", {})
    home, away = teams.get("home", {}), teams.get("away", {})
    venue = raw.get("venue", {})
    official_date = raw.get("officialDate")
    return ScheduledGame(
        game_pk=game_pk,
        game_date=date.fromisoformat(official_date) if official_date else None,
        start_time_utc=_parse_dt(raw.get("gameDate")),
        status=_normalize_status(raw.get("status", {})),
        home_team_id=home.get("team", {}).get("id"),
        home_team_name=home.get("team", {}).get("name"),
        away_team_id=away.get("team", {}).get("id"),
        away_team_name=away.get("team", {}).get("name"),
        venue_id=venue.get("id"),
        venue_name=venue.get("name"),
        home_probable_pitcher=_parse_pitcher(home.get("probablePitcher")),
        away_probable_pitcher=_parse_pitcher(away.get("probablePitcher")),
        home_score=home.get("score"),
        away_score=away.get("score"),
    )


def _normalize_status(status: dict) -> str:
    detailed = str(status.get("detailedState", "")).lower()
    if "postpon" in detailed:
        return "postponed"
    if "cancel" in detailed:
        return "cancelled"
    abstract = status.get("abstractGameState")
    return {"Preview": "scheduled", "Live": "in_progress", "Final": "final"}.get(abstract, "scheduled")


def _parse_pitcher(raw: dict | None) -> ProbablePitcher:
    if not raw:
        return ProbablePitcher(player_id=None, full_name=None)
    return ProbablePitcher(player_id=raw.get("id"), full_name=raw.get("fullName"))


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))
