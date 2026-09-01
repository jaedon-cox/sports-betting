"""Append-only Supabase writers (§3, §5 of the backend/frontend/db doc).

No business logic lives here — every function shapes a row and calls
PostgREST via `PostgrestClient`. Reads for the frontend go straight to
Postgres through Supabase's client libraries; there is no REST read
layer in this package (§4.5).
"""

from __future__ import annotations

from sbm.store.budget import get_month_credits_used, record_odds_usage
from sbm.store.client import PostgrestClient
from sbm.store.facts import (
    GameRow,
    ResultRow,
    SettlementRow,
    TeamRow,
    upsert_games,
    upsert_teams,
    write_results,
    write_settlements,
)
from sbm.store.pipeline_health import finish_pipeline_run, start_pipeline_run
from sbm.store.runs import PickRow, publish_run
from sbm.store.snapshots import (
    InjurySnapshotRow,
    LineSnapshotRow,
    LineupSnapshotRow,
    RawSnapshotRow,
    WeatherSnapshotRow,
    insert_injury_snapshots,
    insert_line_snapshots,
    insert_lineup_snapshots,
    insert_raw_snapshots,
    insert_weather_snapshots,
)

__all__ = [
    "GameRow",
    "InjurySnapshotRow",
    "LineSnapshotRow",
    "LineupSnapshotRow",
    "PickRow",
    "PostgrestClient",
    "RawSnapshotRow",
    "ResultRow",
    "SettlementRow",
    "TeamRow",
    "WeatherSnapshotRow",
    "finish_pipeline_run",
    "get_month_credits_used",
    "insert_injury_snapshots",
    "insert_line_snapshots",
    "insert_lineup_snapshots",
    "insert_raw_snapshots",
    "insert_weather_snapshots",
    "publish_run",
    "record_odds_usage",
    "start_pipeline_run",
    "upsert_games",
    "upsert_teams",
    "write_results",
    "write_settlements",
]
