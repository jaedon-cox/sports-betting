"""The wrapper every scheduled job runs inside, and the CLI that dispatches it.

Backend doc §2.4's failure handling is two-layered: GitHub's built-in
workflow-failure email, plus "a `pipeline_runs` table row at start/end of every
job (queryable health; lets the frontend show 'picks pending' not an empty
state)". This module is the second layer — no job writes that pair itself, so
none can forget the finish row on the error path.

**A `guard` only applies to `schedule` events.** A `workflow_dispatch` is an
operator deliberately re-running a job, usually at the wrong hour on purpose
(a backfill, a retry after a fix); refusing it because the ET clock says 3pm
would make every manual recovery impossible. The workflows run the same check
in a cheap pre-step so a skipped duplicate never pays for a dependency install;
this one is the authoritative copy.

**A `guard` runs before the start row, deliberately.** Every ET-sensitive
workflow schedules two crons so DST cannot shift its hour (`clock.py`), and the
one that isn't the intended trigger must leave no trace: a `pipeline_runs` row
per skipped duplicate would double the table and make "did Job A run today?"
unanswerable by a simple count. An *in-job* skip is different and does write a
row — Job E checking the schedule and finding no game in the closing window did
exactly what it was scheduled to do.

Exit codes are the workflow's signal: 0 succeeded or skipped, 1 failed. A
failure is re-raised after the row is written so the traceback reaches the
Actions log, where an operator debugging the email will look.
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from collections.abc import Callable

from sbm.jobs.context import JobContext, build_context
from sbm.store.pipeline_health import finish_pipeline_run, start_pipeline_run

JobFn = Callable[[JobContext], str]
"""Takes the wiring, returns a one-line human summary for the Actions log."""

GuardFn = Callable[[JobContext], bool]
"""False means "this invocation was not the intended trigger" — see above."""

_ERROR_LIMIT = 2000
"""`pipeline_runs.error_message` is TEXT, but a 100kB traceback in a health
table helps nobody; the full one goes to the Actions log."""

JOB_MODULES: dict[str, str] = {
    "a": "sbm.jobs.job_a_daily_pull",
    "b": "sbm.jobs.job_b_intraday",
    "c": "sbm.jobs.job_c_projected",
    "d": "sbm.jobs.job_d_confirmed",
    "e": "sbm.jobs.job_e_closing_lines",
    "f": "sbm.jobs.job_f_settlement",
    "g": "sbm.jobs.job_g_backtest",
    "h": "sbm.jobs.job_h_heartbeat",
    "i": "sbm.jobs.job_i_statcast",
}
"""Job letter -> module. Each module exposes `JOB_NAME`, `run` and optionally
`guard`. Imported lazily so `python -m sbm.jobs h` does not import pandas."""


def execute(
    job_name: str,
    fn: JobFn,
    *,
    guard: GuardFn | None = None,
    ctx: JobContext | None = None,
) -> int:
    """Run one job between its `pipeline_runs` start and finish rows."""
    context = ctx or build_context()
    if guard is not None and _is_scheduled() and not guard(context):
        print(f"{job_name}: not the intended trigger for this ET time — exiting (no run row)")
        return 0

    run_id = start_pipeline_run(context.client, job_name)
    try:
        summary = fn(context)
    except Exception as exc:  # noqa: BLE001 — every failure must reach the health table
        finish_pipeline_run(
            context.client,
            run_id,
            status="failed",
            error_message=f"{type(exc).__name__}: {exc}"[:_ERROR_LIMIT],
        )
        traceback.print_exc()
        return 1
    finish_pipeline_run(context.client, run_id, status="success")
    print(f"{job_name}: {summary}")
    return 0


def _is_scheduled() -> bool:
    """Cron fired this, rather than a person. Absent locally, where a run is
    always deliberate — GitHub always sets it."""
    return os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") == "schedule"


def main(argv: list[str] | None = None) -> int:
    """`python -m sbm.jobs <letter>` — the one line every workflow runs."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0].lower() not in JOB_MODULES:
        print(f"usage: python -m sbm.jobs {{{'|'.join(sorted(JOB_MODULES))}}}", file=sys.stderr)
        return 2
    module = importlib.import_module(JOB_MODULES[args[0].lower()])
    return execute(module.JOB_NAME, module.run, guard=getattr(module, "guard", None))
