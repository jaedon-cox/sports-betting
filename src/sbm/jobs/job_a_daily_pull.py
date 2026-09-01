"""Job A — daily data pull, ~8am ET (backend doc §2.4).

Schedule + probables, teams, weather forecast, and **the day's one opening odds
snapshot**. That last item is the anchor for everything downstream: §2.5's
budget affords 2 snapshots per game, so this open and Job E's close are the
entire line history, and every pick's `bet_prob` is priced against the number
captured here. Jobs C and D re-price against it rather than buying their own,
which is why the cadence stays inside 500 credits/month.

The pybaseball/Statcast batch named in §2.1 is deliberately not here: those
pulls are disk-cached bulk history with no leakage risk, explicitly excluded
from `raw_snapshots` by §3.6, and they belong to the feature layer's own cache
rather than to a job that must finish before the slate is priced. Wiring them
is a `ingest`-side call once `features/` has a snapshot source to read them
through (see `job_c_projected.py`).

DST: the workflow schedules this twice (12:00 and 13:00 UTC) so it lands at 8am
ET on both sides of the changeover; `guard` drops whichever trigger is not the
intended one. See `clock.py`.
"""

from __future__ import annotations

from sbm.jobs.archive import drain
from sbm.jobs.clock import is_intended_run
from sbm.jobs.context import JobContext
from sbm.jobs.odds_sweep import assert_slate_integrity, sweep
from sbm.jobs.revalidate import revalidate_publish
from sbm.jobs.slate import write_slate_status
from sbm.jobs.slate_ingest import ingest_slate
from sbm.jobs.weather_pull import pull_weather
from sbm.sports.mlb.ingest.archive import CaptureList
from sbm.sports.mlb.ingest.statsapi import StatsApiClient

JOB_NAME = "job_a_daily_pull"
TARGET_ET_HOUR = 8


def guard(ctx: JobContext) -> bool:
    return is_intended_run(ctx.now, TARGET_ET_HOUR)


def run(ctx: JobContext) -> str:
    sport, slate_date = ctx.config.sport, ctx.slate_date
    capture = CaptureList()

    with StatsApiClient() as stats:
        slate = ingest_slate(
            ctx.client, stats=stats, sport=sport, slate_date=slate_date, capture=capture
        )
        if not slate.games:
            # An off-day is a fact worth publishing, not an empty page: the
            # frontend otherwise cannot tell it from a pipeline that died before
            # the schedule pull (`slate.py`).
            write_slate_status(
                ctx.client, sport=sport, slate_date=slate_date, status="no_games", n_games=0
            )
            drain(ctx.client, capture)
            _revalidate(ctx)
            return f"{slate_date}: no games on the slate"
        weather_rows = pull_weather(ctx.client, stats=stats, slate=slate, now=ctx.now, capture=capture)

    result = sweep(
        ctx.client,
        budget=ctx.budget(),
        api_key=ctx.config.require_odds_api_key(),
        slate=slate,
        sport=sport,
        now=ctx.now,
        endpoint_label="odds/mlb/open",
    )
    raw_rows = drain(ctx.client, capture)
    write_slate_status(
        ctx.client,
        sport=sport,
        slate_date=slate_date,
        status="pending",
        n_games=len(slate.games),
    )
    _revalidate(ctx)
    assert_slate_integrity(result)
    return (
        f"{slate_date}: {len(slate.games)} games, {weather_rows} weather rows, "
        f"{result.rows_written} opening line rows ({result.credits} credits), "
        f"{raw_rows} raw snapshots, skips={result.skipped_by_reason}"
    )


def _revalidate(ctx: JobContext) -> None:
    """The games count and slate status both feed the Today's Picks board, so
    they are behind the `slate` tag even though no pick has been written yet."""
    site_url, secret = ctx.config.require_revalidate()
    revalidate_publish(site_url, secret)
