"""Roster + IL status (backend doc §2.1, job B: hourly 10am ET -> first pitch).

The 40-man roster endpoint doubles as the injury feed: each player's `status`
carries an IL code (D7/D10/D15/D60 = injured-list day-count variants, A =
active, ...) plus a free-text `note` describing the injury, so no separate
injuries endpoint is needed.

**Timestamp caveat (model doc §5.1, backend doc §7 item 5, [OPEN]):** this
module returns the roster as of the moment it's called — the *point-in-time
availability* guarantee comes from wrapping this in a `raw_snapshots` row with
`pulled_at_utc`, not from anything StatsAPI tells us. Whether StatsAPI's
underlying status changes reflect true public-availability time (vs.
batch-updated internal time) is unvalidated — flagged upstream, not solved
here.
"""

from __future__ import annotations

from dataclasses import dataclass

from sbm.sports.mlb.ingest.archive import (
    ENTITY_ROSTER,
    SOURCE_STATSAPI,
    CaptureSink,
    capture_payload,
)
from sbm.sports.mlb.ingest.statsapi.client import StatsApiClient

TRUE_IL_STATUS_CODES = frozenset({"D7", "D10", "D15", "D60"})
"""StatsAPI codes that mean "on the injured list." Deliberately excludes
optioned-to-minors/restricted-list codes, which affect availability but are
not injuries."""


@dataclass(frozen=True, slots=True)
class RosterEntry:
    """One `injury_snapshots`-relevant roster row (backend doc §3.2)."""

    player_id: int
    full_name: str
    team_id: int
    position: str | None
    status_code: str | None
    status_description: str | None
    note: str | None

    @property
    def is_injured(self) -> bool:
        return self.status_code in TRUE_IL_STATUS_CODES


def fetch_roster(
    team_id: int,
    *,
    client: StatsApiClient,
    capture: CaptureSink | None = None,
) -> list[RosterEntry]:
    """Pass `capture=` to archive the untouched payload to `raw_snapshots`.

    This is the one that matters most for §2.1: the module docstring's
    point-in-time guarantee *is* the `pulled_at_utc` on that archived row —
    nothing in the parsed `RosterEntry` records when we learned a player was
    on the IL.
    """
    payload = client.get(f"/teams/{team_id}/roster", params={"rosterType": "40Man"})
    capture_payload(
        capture,
        payload,
        source=SOURCE_STATSAPI,
        entity_type=ENTITY_ROSTER,
        entity_id=str(team_id),
    )
    entries = []
    for raw in payload.get("roster", []):
        entry = _parse_entry(raw, team_id)
        if entry is not None:
            entries.append(entry)
    return entries


def _parse_entry(raw: dict, team_id: int) -> RosterEntry | None:
    person = raw.get("person", {})
    player_id = person.get("id")
    if player_id is None:
        return None  # can't identify the player — skip, don't crash the pull
    status = raw.get("status", {})
    return RosterEntry(
        player_id=player_id,
        full_name=person.get("fullName", ""),
        team_id=raw.get("parentTeamId", team_id),
        position=raw.get("position", {}).get("abbreviation"),
        status_code=status.get("code"),
        status_description=status.get("description"),
        note=raw.get("note"),
    )
