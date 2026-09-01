"""Draining `ingest`'s capture seam into `raw_snapshots` (backend doc §2.1).

§2.1 requires that "every ingested blob lands in an append-only
`raw_snapshots(payload jsonb, pulled_at_utc)` table — never mutated." Every
fetcher parses its response and drops the bytes, so a caller cannot satisfy
that after the fact; `sports/mlb/ingest/archive.py` therefore hands the sink
*down into* the fetch as `capture=`. That seam was built and, until this
module, nothing called it — §2.1 was satisfiable but unsatisfied.

`RawCapture`'s fields are 1:1 with `store.snapshots.RawSnapshotRow` precisely
so this translation is a one-liner and `ingest` never has to import `store`.

**The Odds API is archived differently, and deliberately.** `fetch_odds` has no
`capture=` parameter and must not grow one: `sbm.odds.theoddsapi` would then
import `sbm.sports.mlb.ingest.archive`, while
`sbm.sports.mlb.ingest.statsapi.teams` already imports `sbm.odds.resolution` —
a package cycle. `fetch_odds` returns its raw payload instead, so the job
archives it here, at the one call site that holds both the bytes and a DB
client. Its payload is a JSON *array*; `raw_snapshots.payload` is a JSONB
object and `RawSnapshotRow.payload` is typed `dict`, so it is wrapped under a
"games" key rather than coerced.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from sbm.sports.mlb.ingest.archive import SPORT, CaptureList
from sbm.store.client import PostgrestClient
from sbm.store.snapshots import RawSnapshotRow, insert_raw_snapshots

SOURCE_THE_ODDS_API = "the_odds_api"
ENTITY_ODDS = "odds"


def drain(client: PostgrestClient, capture: CaptureList) -> int:
    """Write everything a fetch captured; returns the row count.

    One batched insert per pull rather than one per response — `CaptureList`
    exists for exactly this. Returns 0 (and issues no request) for an empty
    capture, so a job that fetched nothing writes nothing.
    """
    rows = [RawSnapshotRow(**asdict(capture_row)) for capture_row in capture.captures]
    insert_raw_snapshots(client, rows)
    return len(rows)


def archive_odds_payload(
    client: PostgrestClient,
    payload: list[dict[str, Any]],
    *,
    entity_id: str,
    pulled_at_utc: datetime,
) -> None:
    """Archive one raw Odds API response (module docstring for why it is here).

    `entity_id` should identify the pull, not a game — the response is
    slate-wide and spans The Odds API's whole upcoming window, so the useful
    key is when it was taken (e.g. "2026-09-01T23:05:00+00:00/close").
    """
    insert_raw_snapshots(
        client,
        [
            RawSnapshotRow(
                sport=SPORT,
                source=SOURCE_THE_ODDS_API,
                entity_type=ENTITY_ODDS,
                entity_id=entity_id,
                payload={"games": payload},
                pulled_at_utc=pulled_at_utc,
            )
        ],
    )
