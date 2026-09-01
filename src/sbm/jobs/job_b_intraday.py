"""Job B — intraday refresh, hourly 10am ET -> first pitch (backend doc §2.4).

Roster/IL only. This is the cheapest job in the system and the one that runs
most often, so it does exactly one thing: re-pull every slate team's 40-man
roster, archive the untouched payloads to `raw_snapshots` (§2.1), and index the
non-active players into `injury_snapshots` (see `roster_pull.py` for why only
those, and what the point-in-time read rule therefore is).

**Lineup confirmations, which §2.4 also lists here, are not implemented — and
that is a gap in `ingest`, not an omission here.** `features/builder.py` states
it: "No lineup-order ingest yet, so 'confirmed-lineup delta vs projected'
(model doc §10.2) has no source". `store` has `insert_lineup_snapshots` and
`db` has the table, so the writer half exists on both sides; what is missing is
a fetcher between them. Approximating a lineup from the 40-man roster would put
fabricated batting orders into an append-only table, so this writes none.
Reported to `main`/`ingest`.

No revalidation: nothing this job writes is read by any frontend view.

DST: the workflow schedules the union of both offsets' UTC hours and
`is_within_et_hours` trims the one that falls outside the ET range — a range
cadence needs no duplicate-trigger guard, unlike Job A's single instant.
"""

from __future__ import annotations

from sbm.jobs.archive import drain
from sbm.jobs.clock import is_within_et_hours
from sbm.jobs.context import JobContext
from sbm.jobs.roster_pull import pull_rosters
from sbm.jobs.slate_ingest import ingest_slate
from sbm.sports.mlb.ingest.archive import CaptureList
from sbm.sports.mlb.ingest.statsapi import StatsApiClient

JOB_NAME = "job_b_intraday"

START_ET_HOUR = 10
"""§2.4's "10am ET"."""

END_ET_HOUR = 22
"""§2.4 says "-> first pitch", and for a whole slate that is the *last* one: the
West-coast wave starts ~10pm ET, and a scratch announced at 9pm is exactly the
kind of point-in-time fact this job exists to capture. Stopping at Job D's
6:15pm lock would be cheaper and would still serve the official pick, but it
would leave a four-hour hole in the reconstruction history every night."""


def guard(ctx: JobContext) -> bool:
    return is_within_et_hours(ctx.now, START_ET_HOUR, END_ET_HOUR)


def run(ctx: JobContext) -> str:
    sport, slate_date = ctx.config.sport, ctx.slate_date
    capture = CaptureList()
    with StatsApiClient() as stats:
        slate = ingest_slate(
            ctx.client, stats=stats, sport=sport, slate_date=slate_date, capture=capture
        )
        if not slate.games:
            drain(ctx.client, capture)
            return f"{slate_date}: no games — nothing to refresh"
        injury_rows = pull_rosters(
            ctx.client, stats=stats, slate=slate, now=ctx.now, capture=capture
        )
    raw_rows = drain(ctx.client, capture)
    return (
        f"{slate_date}: {len(slate.games)} games, {injury_rows} injury rows, "
        f"{raw_rows} raw snapshots"
    )
