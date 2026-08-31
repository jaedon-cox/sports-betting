"""Odds-budget usage ledger (db/migrations/008_odds_budget_usage.sql):
persists The Odds API credit spend across ephemeral GitHub Actions runs
(§2.5) — each job invocation is a fresh filesystem, so there's nowhere
local to keep a running counter between the ~6 daily cron invocations
that spend credits. `ingest`'s odds/budget.py calls record_odds_usage()
*before* issuing each priced call, not after it succeeds -- a crash
mid-request would otherwise spend a credit the ledger never recorded,
and the cap only holds if it errs toward over-counting.
get_month_credits_used() is read before deciding whether headroom
remains for another one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sbm.store.client import PostgrestClient


def record_odds_usage(
    client: PostgrestClient,
    *,
    month_key: str,
    credits: int,
    endpoint: str,
    called_at_utc: datetime | None = None,
) -> None:
    """Append one ledger row. `month_key` is The Odds API's own reset-cycle
    month (e.g. '2026-08', UTC) — a caller-supplied key, not derived here,
    since it doesn't necessarily match the ET slate month. `called_at_utc`
    is optional: pass it for a reproducible/testable timestamp (as
    `sbm.odds.budget_store.SupabaseUsageStore` does), or omit it to let
    the column's DEFAULT now() apply."""
    row: dict[str, Any] = {"month_key": month_key, "credits": credits, "endpoint": endpoint}
    if called_at_utc is not None:
        row["called_at_utc"] = called_at_utc.isoformat()
    client.insert("odds_budget_usage", [row])


def get_month_credits_used(client: PostgrestClient, month_key: str) -> int:
    """Sum of credits spent so far this month, via fn_odds_budget_month_total
    — a small RPC rather than a generic filtered-select method on
    PostgrestClient, since this is the only aggregate read this package
    needs to expose."""
    return int(client.rpc("fn_odds_budget_month_total", {"p_month_key": month_key}))
