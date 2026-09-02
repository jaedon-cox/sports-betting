"""Job C — model run, Pass A: projected lineups (~3h pre-game, §2.4).

The research/early-signal pass. It is **not** the official pick: `model_runs`
is one row per (run_date, pass_type) and `v_todays_picks` filters strictly to
`pass_type = 'confirmed'`, so nothing this job publishes reaches the board.
Both passes are retained so the confirmed-lineup delta (model doc §10.2) is
measurable rather than asserted — which is the entire reason this job exists.

It therefore writes no `slate_status` row and fires no revalidation: nothing a
frontend view reads changes.

**Timing is per-slate, not per-game.** §2.4's "~3h pre-game" cannot be honoured
for every start time by a single daily run — the board spans day games through
the ~10pm ET West-coast wave — and the `model_runs` grain is one row for the
whole slate. The cron is set ~3h before the ~7pm cluster, the largest one;
earlier games get a shorter lead and later ones a longer one, and
`picks.pick_locked_at` records what each actually was. For the research pass
that is a fair trade. Job D carries the same caveat and it matters more there.

**Features come from `PostgrestSnapshotSource`** (wired 2026-09-02, replacing
the `_UnwiredSnapshotSource` that used to make this job fail by design). Every
value it returns derives from rows strictly earlier than `as_of`, enforced in
SQL rather than by convention — see `features/source/`.

The one thing this job must keep supplying is the slate context: which clubs
are playing, who the probable starters are, and the venue facts. None of that
is in the database at pick time, so `jobs/feature_source.build_source` gathers
it from the schedule pull above.
"""

from __future__ import annotations

from sbm.jobs.archive import drain
from sbm.jobs.clock import is_intended_run
from sbm.jobs.context import JobContext
from sbm.jobs.feature_source import build_source
from sbm.jobs.model_pass import run_pass
from sbm.jobs.slate_ingest import ingest_slate
from sbm.sports.mlb.features import MLBFeatureBuilder
from sbm.sports.mlb.ingest.archive import CaptureList
from sbm.sports.mlb.ingest.statsapi import StatsApiClient

JOB_NAME = "job_c_projected"
PASS_TYPE = "projected"
TARGET_ET_HOUR = 16


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
            drain(ctx.client, capture)
            return f"{slate_date}: no games — nothing to score"
        # Built inside the client block: the venue lookups it makes need the
        # same throttled StatsAPI session the schedule pull used.
        source = build_source(
            ctx.client, stats=stats, slate=slate, team_codes=slate.team_codes
        )
    drain(ctx.client, capture)

    result = run_pass(ctx, slate, pass_type=PASS_TYPE, builder=MLBFeatureBuilder(source=source))
    return (
        f"{slate_date} pass={PASS_TYPE} run={result.model_run_id}: {result.n_picks} picks "
        f"({result.n_recommended} recommended) over {result.n_games} games, "
        f"skips={result.skipped}"
    )
