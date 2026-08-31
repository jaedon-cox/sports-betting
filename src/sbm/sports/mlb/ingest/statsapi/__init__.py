"""MLB StatsAPI ingest — schedule, probables, roster/IL, live+final scores."""

from __future__ import annotations

from sbm.sports.mlb.ingest.statsapi.client import StatsApiClient
from sbm.sports.mlb.ingest.statsapi.roster import RosterEntry, fetch_roster
from sbm.sports.mlb.ingest.statsapi.schedule import (
    FinalResult,
    ProbablePitcher,
    ScheduledGame,
    extract_final_results,
    fetch_schedule,
)
from sbm.sports.mlb.ingest.statsapi.teams import (
    build_external_game_id_resolver,
    compose_internal_resolver,
)
from sbm.sports.mlb.ingest.statsapi.venue import VenueInfo, fetch_venue

__all__ = [
    "FinalResult",
    "ProbablePitcher",
    "RosterEntry",
    "ScheduledGame",
    "StatsApiClient",
    "VenueInfo",
    "build_external_game_id_resolver",
    "compose_internal_resolver",
    "extract_final_results",
    "fetch_roster",
    "fetch_schedule",
    "fetch_venue",
]
