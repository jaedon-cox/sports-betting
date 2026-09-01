"""Job E — closing-line capture (backend doc §2.4/§2.5). The CLV anchor.

**Why this is six cron triggers and not a poller.** MLB start times stagger
across the day, so a fixed "poll every N minutes" timer either misses each
game's actual close or runs for ~13 hours. GitHub bills whole-minute increments
*per invocation*, so polling frequency — not job runtime — is the cost driver:
§2.2 measured the original 5-minute checker at ~150 billed min/day, which blows
the 2000/month cap in about a week. So each trigger sits at a known start-time
cluster, makes one free StatsAPI schedule check, sweeps only if a game is
actually inside its closing window, and exits.

**DST needs no wall-clock guard here, unlike Jobs A–D.** The window test
compares UTC instants (`games.start_time_utc` against `now`), so it is correct
whatever the offset. A trigger that fires an hour off simply finds no game in
window and costs one billed minute. The workflow still adds November-only
hedge triggers, because under EST the evening clusters move an hour later in
UTC and would otherwise have no trigger near them at all.

**The window is T-20 to T-1, not T-5.** §2.5 and model doc §7 define the close
as the T-5min Pinnacle price, but a scheduled workflow is queued rather than
guaranteed and can start many minutes late. A 19-minute window absorbs that and
already contains §2.5's documented fallback tolerance (T-15 -> T-2 on a
5+-cluster night). Sweeping *after* first pitch would capture an in-play price
and quietly corrupt every CLV number it touched, which is why the near edge is
T-1 rather than 0.

**A skipped sweep is a budget decision, not a failure.** `PaceGuard` refuses a
discretionary call that would spend the month ahead of schedule; §2.5 names
that precision-for-budget tradeoff explicitly. The open snapshot Job A takes is
never paced.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sbm.jobs.archive import drain
from sbm.jobs.context import JobContext
from sbm.jobs.odds_sweep import CREDITS_PER_SWEEP, assert_slate_integrity, sweep
from sbm.jobs.pacing import PaceGuard
from sbm.jobs.revalidate import revalidate_publish
from sbm.jobs.slate_ingest import Slate, ingest_slate
from sbm.sports.mlb.ingest.archive import CaptureList
from sbm.sports.mlb.ingest.statsapi import StatsApiClient

JOB_NAME = "job_e_closing_lines"

WINDOW_FAR = timedelta(minutes=20)
WINDOW_NEAR = timedelta(minutes=1)


def run(ctx: JobContext) -> str:
    sport, slate_date = ctx.config.sport, ctx.slate_date
    capture = CaptureList()
    with StatsApiClient() as stats:
        slate = ingest_slate(
            ctx.client, stats=stats, sport=sport, slate_date=slate_date, capture=capture
        )
    drain(ctx.client, capture)

    closing = closing_window_games(slate, ctx.now)
    if not closing:
        return f"{slate_date}: no game inside the closing window — exiting"

    budget = ctx.budget()
    pace = PaceGuard(budget=budget, daily_credits=ctx.config.daily_odds_credits)
    if not pace.allows(CREDITS_PER_SWEEP, ctx.now):
        return (
            f"{slate_date}: {len(closing)} game(s) at close, but the month is at pace "
            f"(headroom {pace.headroom(ctx.now)} credits) — sweep skipped per §2.5"
        )

    result = sweep(
        ctx.client,
        budget=budget,
        api_key=ctx.config.require_odds_api_key(),
        slate=slate,
        sport=sport,
        now=ctx.now,
        closing_external_ids=closing,
        endpoint_label="odds/mlb/close",
    )
    site_url, secret = ctx.config.require_revalidate()
    revalidate_publish(site_url, secret)
    assert_slate_integrity(result)
    return (
        f"{slate_date}: swept {len(closing)} closing game(s), {result.closing_rows} closing rows "
        f"of {result.rows_written} total ({result.credits} credits), skips={result.skipped_by_reason}"
    )


def closing_window_games(slate: Slate, now: datetime) -> frozenset[str]:
    """gamePks whose first pitch is inside [now + T-20, now + T-1].

    Games with no known start time are excluded rather than assumed imminent:
    flagging a snapshot `is_closing` on a guess would make it the number CLV is
    measured against.
    """
    out = set()
    for game in slate.games:
        start = game.start_time_utc
        if start is None:
            continue
        lead = start - now
        if WINDOW_NEAR <= lead <= WINDOW_FAR:
            out.add(str(game.game_pk))
    return frozenset(out)
