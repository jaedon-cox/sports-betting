"""40-man roster/IL sweep -> `injury_snapshots` (Job B, §2.1/§2.4).

MLB StatsAPI's roster endpoint doubles as the injury feed, so this is one call
per team on the slate — no separate injuries endpoint.

**Only non-active players are written, and that is a storage decision with a
consequence.** A row per 40-man player per hourly pull is ~1,200 rows/hour, or
well over 2M a season — enough to dominate the 500 MB free tier that §3.6's
retention plan is built around. Filtering to `status_code != 'A'` cuts that by
roughly 30x while keeping every player whose availability is actually in
question (the IL codes plus optioned/restricted/suspended).

The consequence: a player returning to active writes no row, so the naive
"latest `injury_snapshots` row at `as_of`" read would report them still hurt.
The correct point-in-time rule is therefore *"a player with no non-active row
at-or-after their team's most recent pull before `as_of` is available"* — the
pull cadence is what makes absence meaningful. The full 40-man payload is
archived to `raw_snapshots` on every pull regardless (§2.1), so the complete
state is always reconstructible even though the typed table is an index of the
exceptions. Flagged to `ingest`/`db`: if the feature layer would rather have
explicit reinstatement rows, that needs a read-before-write and belongs in
their layer, not here.

`RosterEntry.is_injured` remains the narrower true-IL test (D7/D10/D15/D60);
this writes the wider availability set and leaves that distinction to the
`status` string the feature layer reads.
"""

from __future__ import annotations

from datetime import datetime

from sbm.jobs.slate_ingest import Slate
from sbm.sports.mlb.ingest.archive import CaptureList
from sbm.sports.mlb.ingest.statsapi import RosterEntry, StatsApiClient, fetch_roster
from sbm.store.client import PostgrestClient
from sbm.store.snapshots import InjurySnapshotRow, insert_injury_snapshots

ACTIVE_STATUS_CODE = "A"


def pull_rosters(
    client: PostgrestClient,
    *,
    stats: StatsApiClient,
    slate: Slate,
    now: datetime,
    capture: CaptureList | None = None,
) -> int:
    """One roster pull per team on today's slate; returns rows written."""
    rows: list[InjurySnapshotRow] = []
    for statsapi_team_id in _teams_on_slate(slate):
        team_id = slate.team_ids.get(statsapi_team_id)
        if team_id is None:
            continue  # team not in `teams` yet — Job A's upsert has not run
        for entry in fetch_roster(statsapi_team_id, client=stats, capture=capture):
            if entry.status_code == ACTIVE_STATUS_CODE:
                continue
            rows.append(_row(entry, team_id, now))
    insert_injury_snapshots(client, rows)
    return len(rows)


def _teams_on_slate(slate: Slate) -> list[int]:
    """StatsAPI team ids playing today, deduplicated and order-stable.

    A doubleheader puts the same pair on the slate twice; pulling their roster
    twice would double the request count against a 1 req/s throttle for
    identical data.
    """
    seen: dict[int, None] = {}
    for game in slate.games:
        for team_id in (game.home_team_id, game.away_team_id):
            if team_id is not None:
                seen.setdefault(team_id, None)
    return list(seen)


def _row(entry: RosterEntry, team_id: int, now: datetime) -> InjurySnapshotRow:
    return InjurySnapshotRow(
        # TEXT in the schema (§3.2) — player ids are not necessarily numeric
        # across sports, which is the same reason `picks.player_id` is TEXT.
        player_id=str(entry.player_id),
        team_id=team_id,
        status=entry.status_description or entry.status_code or "unknown",
        captured_at_utc=now,
        note=entry.note,
    )
