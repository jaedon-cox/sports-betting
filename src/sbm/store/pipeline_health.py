"""pipeline_runs writer (§2.4 Failure handling): every scheduled job
writes a start row and a finish row so ops has queryable health and the
frontend can show "picks pending" instead of an empty state before the
day's model_runs flips to success. pipeline_runs is one of the
deliberate insert-only exceptions (§3.1) — job status is metadata, not a
decision-bearing value — but this module only ever inserts one row per
job invocation and then updates that same row, never any other.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sbm.store.client import PostgrestClient

_TERMINAL_STATUSES = ("success", "failed")


def start_pipeline_run(client: PostgrestClient, job_name: str) -> int:
    """Insert the 'running' row for one job invocation; returns its id."""
    rows = client.insert("pipeline_runs", [{"job_name": job_name, "status": "running"}])
    return int(rows[0]["run_id"])


def finish_pipeline_run(
    client: PostgrestClient,
    run_id: int,
    *,
    status: str,
    error_message: str | None = None,
) -> None:
    """Flip a job's row to its terminal status."""
    if status not in _TERMINAL_STATUSES:
        raise ValueError(f"finish_pipeline_run status must be one of {_TERMINAL_STATUSES}, got {status!r}")
    client.patch(
        "pipeline_runs",
        match={"run_id": run_id},
        values={"status": status, "finished_at": datetime.now(UTC).isoformat(), "error_message": error_message},
    )
