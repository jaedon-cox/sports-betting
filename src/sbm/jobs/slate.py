"""`slate_status` — the row that tells "no games today" from "not published yet".

`v_todays_picks` selects the latest *successful* run, so it keeps serving the
last known-good slate when today's run dies or hasn't finished (backend doc
§2.4's atomic-publish guarantee, and the reason the frontend never renders half
a slate). The cost of that guarantee is that "rows exist" no longer means
"today published", and `web/README.md` records the frontend working around it
by counting `games` rows for the ET date — which cannot distinguish an off-day
from a pipeline that died before the schedule pull.

So the pipeline publishes the fact directly. `db` owns the DDL; this module
owns writing the row. Deliberately mutable and upserted per (sport,
slate_date), like `pipeline_runs`: job status is ops metadata, not a
decision-bearing value, so it is one of §3.1's stated exceptions and does not
touch CLAUDE.md rule 5.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from sbm.store.client import PostgrestClient

TABLE = "slate_status"
ON_CONFLICT = "sport,slate_date"

SlateState = Literal["no_games", "pending", "published", "failed"]
"""no_games  — schedule ingest ran and the slate is genuinely empty (off-day).
pending    — games exist; today's confirmed run has not published yet.
published  — today's confirmed run reached status='success'.
failed     — the confirmed run terminated without publishing."""


def write_slate_status(
    client: PostgrestClient,
    *,
    sport: str,
    slate_date: date,
    status: SlateState,
    n_games: int,
    model_run_id: int | None = None,
) -> None:
    """Upsert one slate's status.

    `model_run_id` is set only by `published`, and is what lets the frontend
    read the publish time from `model_runs.updated_at` — the "generated at
    HH:MM ET" banner — without guessing which run produced the board.

    It is always sent, explicitly `None` when there is none, rather than omitted
    from the row. PostgREST upserts with `resolution=merge-duplicates`, so an
    omitted column keeps whatever the existing row held: a `pending` or `failed`
    write landing after a `published` one for the same date (a manual Job A
    re-run, say) would flip the status while leaving the old run id attached, and
    the frontend would read a publish time for a slate this table says is not
    published. `db`'s `CHECK (status <> 'published' OR model_run_id IS NOT NULL)`
    does not catch that direction, so nothing would report it (`db` raised this;
    sending the key makes each write fully describe the row it produces).
    """
    row: dict[str, Any] = {
        "sport": sport,
        "slate_date": slate_date.isoformat(),
        "status": status,
        "n_games": n_games,
        "model_run_id": model_run_id,
    }
    client.upsert(TABLE, [row], on_conflict=ON_CONFLICT)
