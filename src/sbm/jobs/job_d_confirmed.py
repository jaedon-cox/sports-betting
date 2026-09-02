"""Job D — model run, Pass B: confirmed lineups (~T-45min, §2.4). The official pick.

This is the run CLV is measured against. Its picks are what `v_todays_picks`
serves, its `model_runs.updated_at` is the frontend's "generated at HH:MM ET"
banner, and its `picks.market_fair_prob` becomes `pick_settlements.bet_prob`
when Job F settles the night.

**Timing is per-slate.** As in Job C, one daily run cannot be T-45min for every
start time, and `model_runs` is one row per (run_date, pass_type) covering the
whole board (§2.4). The cron sits 45 minutes before the ~7pm ET cluster;
`picks.pick_locked_at` records each pick's real lock instant. This does not
distort CLV — CLV compares the de-vigged price this pick was taken at against
the T-5min close for the same side and book, and both numbers are per-pick.
What it does mean is that a 1pm day game is locked *after* first pitch, so its
"open" price is the 8am snapshot and its lock is nominal. Splitting Job D into
per-cluster runs would fix that at the cost of one `model_runs` row per
cluster, which is a schema-grain change — flagged rather than taken.

**Publishing is atomic and the flip is last.** `publish_run` wraps
`fn_publish_run`, one Postgres function call and therefore one transaction: the
whole slate's picks and the `running -> success` flip land together or not at
all, so a job that dies at game 8 of 15 leaves nothing visible and the frontend
keeps the last known-good slate (§2.4).

Features come from `PostgrestSnapshotSource`, assembled the same way as in
Job C — see that module.
"""

from __future__ import annotations

from sbm.jobs.archive import drain
from sbm.jobs.clock import is_intended_run
from sbm.jobs.context import JobContext
from sbm.jobs.feature_source import build_source
from sbm.jobs.model_pass import run_pass
from sbm.jobs.revalidate import revalidate_publish
from sbm.jobs.slate import write_slate_status
from sbm.jobs.slate_ingest import ingest_slate
from sbm.sports.mlb.features import MLBFeatureBuilder
from sbm.sports.mlb.ingest.archive import CaptureList
from sbm.sports.mlb.ingest.statsapi import StatsApiClient

JOB_NAME = "job_d_confirmed"
PASS_TYPE = "confirmed"
TARGET_ET_HOUR = 18
TARGET_ET_MINUTE = 15


def guard(ctx: JobContext) -> bool:
    return is_intended_run(ctx.now, TARGET_ET_HOUR, TARGET_ET_MINUTE)


def run(ctx: JobContext) -> str:
    sport, slate_date = ctx.config.sport, ctx.slate_date
    capture = CaptureList()
    with StatsApiClient() as stats:
        slate = ingest_slate(
            ctx.client, stats=stats, sport=sport, slate_date=slate_date, capture=capture
        )
        if not slate.games:
            drain(ctx.client, capture)
            write_slate_status(
                ctx.client, sport=sport, slate_date=slate_date, status="no_games", n_games=0
            )
            return f"{slate_date}: no games — nothing to publish"
        # Built inside the client block: the venue lookups it makes need the
        # same throttled StatsAPI session the schedule pull used.
        source = build_source(
            ctx.client, stats=stats, slate=slate, team_codes=slate.team_codes
        )
    drain(ctx.client, capture)

    try:
        result = run_pass(
            ctx, slate, pass_type=PASS_TYPE, builder=MLBFeatureBuilder(source=source)
        )
    except Exception:
        # The frontend must be able to tell "today failed" from "today is still
        # coming"; `pipeline_runs` records the job, `slate_status` records the
        # slate, and only the second is a view the board reads (`slate.py`).
        write_slate_status(
            ctx.client,
            sport=sport,
            slate_date=slate_date,
            status="failed",
            n_games=len(slate.games),
        )
        raise

    write_slate_status(
        ctx.client,
        sport=sport,
        slate_date=slate_date,
        status="published",
        n_games=len(slate.games),
        model_run_id=result.model_run_id,
    )
    site_url, secret = ctx.config.require_revalidate()
    revalidate_publish(site_url, secret)
    return (
        f"{slate_date} pass={PASS_TYPE} run={result.model_run_id}: {result.n_picks} picks "
        f"({result.n_recommended} recommended) over {result.n_games} games, "
        f"skips={result.skipped}"
    )
