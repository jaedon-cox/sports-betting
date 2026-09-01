"""Team reference pull — a temporary bridge that belongs in `ingest`.

`teams.code` is what the frontend renders (`v_todays_picks.home_team_code`,
`v_pick_archive`), so it has to be the real abbreviation — "NYY", not a
surrogate. `statsapi.schedule.ScheduledGame` carries the team *id* and *name*
but no `abbreviation`, and `statsapi/teams.py` builds odds-name resolvers
rather than fetching the reference list, so nothing in `ingest` can supply it
today.

Rather than write "147" into a column users read, or invent a code table that
would go stale, this makes the one `/teams?sportId=1` call directly through
`StatsApiClient` — `ingest`'s public, throttled client, not a private of
theirs. It is still the wrong home for it.

**TODO(ingest): move this to `sports/mlb/ingest/statsapi/teams.py` as
`fetch_teams(*, client, capture=None)`.** It is the same shape as
`fetch_roster`/`fetch_venue` and wants their `capture=` seam; `pipeline` did
not add it there because that directory is `ingest`'s to own (CLAUDE.md team
table). Deleting this module and re-pointing `slate_ingest.py` is the whole
change.
"""

from __future__ import annotations

from sbm.sports.mlb.ingest.statsapi.client import StatsApiClient
from sbm.store.facts import TeamRow

SPORT = "mlb"


def fetch_team_rows(*, client: StatsApiClient) -> dict[int, TeamRow]:
    """All active MLB teams, keyed by StatsAPI team id.

    Keyed by the StatsAPI id because that is what `ScheduledGame` carries and
    what `fetch_roster` takes; the value is what `upsert_teams` writes. Every
    field read is defensive, matching the rest of the StatsAPI ingest: this API
    is unofficial and a shape change should drop one field, not the slate.
    """
    payload = client.get("/teams", params={"sportId": 1, "activeStatus": "Y"})
    rows: dict[int, TeamRow] = {}
    for raw in payload.get("teams", []):
        team_id = raw.get("id")
        code = raw.get("abbreviation")
        name = raw.get("name")
        if team_id is None or not code or not name:
            continue  # unusable without an id and a display code — skip, don't guess
        rows[int(team_id)] = TeamRow(
            sport=SPORT,
            code=str(code),
            name=str(name),
            league=(raw.get("league") or {}).get("name"),
            division=(raw.get("division") or {}).get("name"),
        )
    return rows
