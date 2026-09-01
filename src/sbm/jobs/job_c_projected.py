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

**This job cannot succeed yet, and the failure is the correct behaviour.**
`MLBFeatureBuilder`'s default `SnapshotSource` is `_UnwiredSnapshotSource`,
which raises `NotImplementedError` on every method because `store/` is
write-only and no point-in-time read layer exists (`features/builder.py` says
so in its own docstring). Passing `builder=` here is the whole wiring change
when one lands; until then this fails loudly rather than pricing fabricated
features.
"""

from __future__ import annotations

from sbm.jobs.archive import drain
from sbm.jobs.clock import is_intended_run
from sbm.jobs.context import JobContext
from sbm.jobs.model_pass import run_pass
from sbm.jobs.slate_ingest import ingest_slate
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
    drain(ctx.client, capture)
    if not slate.games:
        return f"{slate_date}: no games — nothing to score"

    result = run_pass(ctx, slate, pass_type=PASS_TYPE)
    return (
        f"{slate_date} pass={PASS_TYPE} run={result.model_run_id}: {result.n_picks} picks "
        f"({result.n_recommended} recommended) over {result.n_games} games, "
        f"skips={result.skipped}"
    )
