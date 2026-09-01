"""Job H — weekly heartbeat, year-round (backend doc §2.4).

The MLB offseason (~Nov-Feb) has no games and no daily pipeline, so the "daily
writes keep Supabase alive" assumption stops holding exactly when nobody is
watching — and a project that auto-pauses after 7 idle days would need a manual
resume before the season's first pull. This is the only job scheduled outside
the season, and its `pipeline_runs` start/finish pair is deliberately the whole
point rather than incidental bookkeeping: it is a write, and it goes over
PostgREST.

That last detail is §7 item 8's open question — whether the 7-day idle timer
keys on API-gateway traffic or on a raw `postgres://` connection is unverified,
and the doc's own hedge is "route at least one daily write through the REST
layer regardless". Everything this job does is REST.

It also reads, through `fn_odds_budget_month_total` — an existing STABLE
function, so this costs one cheap query and returns something worth printing:
if the ledger has drifted or the month is running hot, the weekly log line is
where an operator would see it before the season does.

No revalidation, no odds call, no schedule check. It must keep working when
every upstream source is dark.
"""

from __future__ import annotations

from sbm.jobs.context import JobContext
from sbm.odds.budget import MONTHLY_CREDIT_CAP, month_key
from sbm.store.budget import get_month_credits_used

JOB_NAME = "job_h_heartbeat"


def run(ctx: JobContext) -> str:
    key = month_key(ctx.now)
    used = get_month_credits_used(ctx.client, key)
    return (
        f"alive at {ctx.now.isoformat()} — odds credits {used}/{MONTHLY_CREDIT_CAP} "
        f"used for {key}"
    )
