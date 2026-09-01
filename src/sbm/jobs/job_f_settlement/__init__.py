"""Job F — nightly settlement (backend doc §2.4). Outcomes, CLV, and the rollups.

Four things, and the Model Record page needs all four:

1. final scores into `results` (insert-once, §3.2),
2. one `pick_settlements` row per pick — outcome, `bet_prob`, `closing_prob`
   and RELATIVE `clv_pct` (`outcomes.py`),
3. `calibration_buckets` UPSERTed per rollup date, and the three matviews
   refreshed (`rollups.py`),
4. the frontend's ISR purge for the `record` and `archive` tags.

**This is where live CLV is computed, and the only place it can be.** The close
lands at T-5min, after Job D has already locked the pick, so no pick-time path
can produce it without inventing one. A postponed game or a missed sweep is a
null `closing_prob` here, never a raise.

**Runs at ~4am ET and settles the previous ET slate date.** A 10pm ET West-coast
start finishes after midnight, so a job run "tonight" would grade half the board
as still in progress. Settlement is nonetheless keyed on the *absence* of a
`pick_settlements` row rather than on a date, so a night the job missed is
picked up by the next one without a backfill; only the schedule re-pull is
date-bounded, and it looks back `LOOKBACK_DAYS` for that reason.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from typing import Any

from sbm.jobs.archive import drain
from sbm.jobs.clock import is_intended_run
from sbm.jobs.context import JobContext
from sbm.jobs.job_f_settlement.outcomes import settle_picks, write_settlements
from sbm.jobs.job_f_settlement.rollups import refresh_matviews, upsert_calibration_buckets
from sbm.jobs.revalidate import revalidate_settlement
from sbm.jobs.rpc import record_results, unsettled_picks
from sbm.jobs.slate_ingest import Slate, ingest_slate
from sbm.markets import market_registry
from sbm.sports.mlb.ingest.archive import CaptureList
from sbm.sports.mlb.ingest.statsapi import StatsApiClient, extract_final_results
from sbm.store.facts import ResultRow

JOB_NAME = "job_f_settlement"
TARGET_ET_HOUR = 4

LOOKBACK_DAYS = 2
"""Slate dates whose schedule is re-pulled for final scores and statuses. Two
covers a night this job missed; anything older needs a `workflow_dispatch`
re-run, which is the right amount of ceremony for a backfill."""


def guard(ctx: JobContext) -> bool:
    return is_intended_run(ctx.now, TARGET_ET_HOUR)


def run(ctx: JobContext) -> str:
    sport = ctx.config.sport
    capture = CaptureList()
    with StatsApiClient() as stats:
        slates = [
            ingest_slate(
                ctx.client,
                stats=stats,
                sport=sport,
                slate_date=ctx.slate_date - timedelta(days=offset),
                capture=capture,
            )
            for offset in range(1, LOOKBACK_DAYS + 1)
        ]
    drain(ctx.client, capture)
    n_results = record_results(ctx.client, [row for slate in slates for row in _results(slate)])

    pending = unsettled_picks(ctx.client, sport=sport, before=ctx.now)
    settlements = settle_picks(pending, market_registry())
    n_settled = write_settlements(ctx.client, settlements)

    settled_ids = {row.pick_id for row in settlements}
    rollup_dates = sorted({pick.game_date for pick in pending if pick.pick_id in settled_ids})
    n_buckets = sum(
        upsert_calibration_buckets(ctx.client, sport=sport, rollup_date=day)
        for day in rollup_dates
    )
    refresh_matviews(ctx.client)

    site_url, secret = ctx.config.require_revalidate()
    revalidate_settlement(site_url, secret)
    return (
        f"{n_results} results, {n_settled} settlements over {len(rollup_dates)} date(s), "
        f"{n_buckets} calibration buckets, matviews refreshed"
    )


def _results(slate: Slate) -> list[dict[str, Any]]:
    """Final scores as `results` rows, keyed to `games.id`.

    `ResultRow` is `db`'s own shape, so `fn_record_results` receives exactly the
    columns the table has; a game whose id is not in the slate map is skipped
    rather than keyed to nothing.
    """
    rows = []
    for final in extract_final_results(slate.games):
        game_id = slate.game_ids.get(str(final.game_pk))
        if game_id is None:
            continue
        rows.append(
            asdict(
                ResultRow(
                    game_id=game_id,
                    home_score=final.home_runs,
                    away_score=final.away_runs,
                    final_status=final.final_status,
                )
            )
        )
    return rows
