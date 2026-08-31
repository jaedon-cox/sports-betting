"""The seam that lets an ingest pull be archived to `raw_snapshots`.

Backend doc §2.1: "every ingested blob lands in an append-only
`raw_snapshots(payload jsonb, pulled_at_utc)` table — never mutated." Every
fetcher in this package parses its response into typed rows and then drops
the response, which means a caller *cannot* satisfy §2.1 after the fact —
the bytes are gone by the time the fetcher returns. Re-fetching to archive
would double the request count (and, for The Odds API, the credit spend).

So archiving is a *sink handed down into* the fetch, not a step layered on
top of it: pass `capture=`, and the fetcher hands the untouched payload to
it at the moment it arrives, before any parsing. Omit `capture=` and nothing
changes — the seam costs one `if` and no I/O.

**This module deliberately does not import `sbm.store`.** Writing rows is
`db`'s concern and scheduling the write is `pipeline`'s; `RawCapture`'s
fields are 1:1 with `sbm.store.snapshots.RawSnapshotRow`, so a job wires the
two together with `RawSnapshotRow(**dataclasses.asdict(capture))` without
this package taking a dependency on the storage layer.

**Scope (§3.6):** point-in-time-sensitive categories only — lineups,
injuries, odds, weather (plus schedule, whose probable pitchers move). Bulk
pybaseball/Statcast pulls are explicitly excluded from `raw_snapshots` —
they carry no leakage risk and would dominate the 500 MB free-tier cap — so
`ingest/pybaseball.py` and `ingest/savant.py` have no capture seam by
design, not by omission.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

SPORT = "mlb"

SOURCE_STATSAPI = "mlb_statsapi"
SOURCE_OPEN_METEO = "open_meteo"

ENTITY_SCHEDULE = "schedule"
ENTITY_ROSTER = "roster"
ENTITY_WEATHER = "weather"


@dataclass(frozen=True, slots=True)
class RawCapture:
    """One un-parsed response, with the instant it was pulled.

    `pulled_at_utc` is the only thing that makes the payload point-in-time
    usable: StatsAPI tells us nothing about when a roster change became
    *public*, so the pull time is our sole honest lower bound on what was
    knowable (model doc §5.1, backend doc §7 item 5 — still [OPEN]).

    Field names match `sbm.store.snapshots.RawSnapshotRow` exactly so no
    translation layer is needed (module docstring).
    """

    sport: str
    source: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    pulled_at_utc: datetime


class CaptureSink(Protocol):
    """Where a fetcher hands its raw payload. Implementations must not raise
    on an unexpected shape — an archival failure must never take down the
    pull whose data the rest of the slate depends on."""

    def __call__(self, capture: RawCapture) -> None: ...


def capture_payload(
    capture: CaptureSink | None,
    payload: dict[str, Any],
    *,
    source: str,
    entity_type: str,
    entity_id: str,
) -> None:
    """Hand `payload` to `capture` if one was supplied, stamped with now().

    Called by fetchers immediately after the response lands and *before*
    parsing, so what gets archived is the full-fidelity blob rather than
    whatever survived this repo's defensive `.get()` chain.
    """
    if capture is None:
        return
    capture(
        RawCapture(
            sport=SPORT,
            source=source,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            pulled_at_utc=datetime.now(UTC),
        )
    )


class CaptureList:
    """A `CaptureSink` that just accumulates — for jobs that batch one
    `insert_raw_snapshots` call per pull, and for tests."""

    def __init__(self) -> None:
        self.captures: list[RawCapture] = []

    def __call__(self, capture: RawCapture) -> None:
        self.captures.append(capture)
