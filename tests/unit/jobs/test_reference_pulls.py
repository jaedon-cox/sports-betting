"""Job A's team reference pull and Job B's roster sweep.

Both turn an upstream payload into rows for one table, and both have a
documented *skip* rule — a team with no abbreviation, a player still active.
Those skips are the behaviour worth pinning: each exists so a partial upstream
response degrades a row rather than the slate. `test_weather_pull.py` covers
the third helper, which shares `FakeStats` and `slate_with` from here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sbm.jobs.mlb_reference import fetch_team_rows
from sbm.jobs.roster_pull import pull_rosters
from sbm.jobs.slate_ingest import Slate
from sbm.sports.mlb.ingest.statsapi.roster import RosterEntry
from tests.unit.jobs.fakes import FakeClient
from tests.unit.jobs.test_odds_sweep import game

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


class FakeStats:
    """Stands in for `StatsApiClient` — only `get` is reachable from these
    helpers; `fetch_roster`/`fetch_venue` are monkeypatched at their call site."""

    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {}
        self.calls: list[tuple[str, dict]] = []

    def get(self, path: str, params: dict | None = None) -> dict:
        self.calls.append((path, params or {}))
        return self.payload


def slate_with(*games) -> Slate:
    return Slate(
        slate_date=NOW.date(),
        games=list(games),
        game_ids={str(g.game_pk): 100 + i for i, g in enumerate(games)},
        team_ids={1: 11, 2: 22},
    )


# --------------------------------------------------------------------------
# mlb_reference
# --------------------------------------------------------------------------


def test_team_rows_are_keyed_by_the_statsapi_id_the_schedule_carries() -> None:
    """`ScheduledGame` carries the StatsAPI id; `teams.code` is what the
    frontend renders. This is the only place the two are joined."""
    stats = FakeStats(
        {
            "teams": [
                {
                    "id": 147,
                    "abbreviation": "NYY",
                    "name": "New York Yankees",
                    "league": {"name": "American League"},
                    "division": {"name": "AL East"},
                }
            ]
        }
    )
    rows = fetch_team_rows(client=stats)  # type: ignore[arg-type]
    assert set(rows) == {147}
    assert (rows[147].code, rows[147].name) == ("NYY", "New York Yankees")
    assert (rows[147].league, rows[147].division) == ("American League", "AL East")
    assert stats.calls == [("/teams", {"sportId": 1, "activeStatus": "Y"})]


def test_a_team_missing_a_code_or_name_is_skipped_rather_than_surrogate_keyed() -> None:
    """Writing "147" into a column users read is worse than one missing team."""
    stats = FakeStats(
        {
            "teams": [
                {"id": 1, "name": "No Code"},
                {"id": 2, "abbreviation": "NC", "name": None},
                {"abbreviation": "NI", "name": "No Id"},
                {"id": 4, "abbreviation": "OK", "name": "Fine"},
            ]
        }
    )
    assert set(fetch_team_rows(client=stats)) == {4}  # type: ignore[arg-type]


def test_missing_league_and_division_are_none_not_a_crash() -> None:
    stats = FakeStats({"teams": [{"id": 1, "abbreviation": "AB", "name": "A B"}]})
    row = fetch_team_rows(client=stats)[1]  # type: ignore[arg-type]
    assert (row.league, row.division) == (None, None)


# --------------------------------------------------------------------------
# roster_pull
# --------------------------------------------------------------------------


def entry(player_id: int, status_code: str, description: str | None = None) -> RosterEntry:
    return RosterEntry(
        player_id=player_id,
        full_name=f"Player {player_id}",
        team_id=1,
        position="P",
        status_code=status_code,
        status_description=description,
        note=None,
    )


def test_only_non_active_players_are_written(monkeypatch) -> None:
    """A row per 40-man player per hourly pull would be >2M rows a season
    against a 500 MB free tier (§3.6); the table is an index of exceptions."""
    monkeypatch.setattr(
        "sbm.jobs.roster_pull.fetch_roster",
        lambda team_id, *, client, capture=None: [
            entry(1, "A"), entry(2, "D60", "60-Day IL"), entry(3, "RM")
        ],
    )
    client = FakeClient()
    written = pull_rosters(
        client, stats=FakeStats(), slate=slate_with(game(555, "HOM", "AWY")), now=NOW  # type: ignore[arg-type]
    )
    assert written == 4  # two teams on the slate x two non-active players
    ids = {row["player_id"] for row in client.rows_for("injury_snapshots")}
    assert ids == {"2", "3"}


def test_player_ids_are_written_as_text(monkeypatch) -> None:
    """`injury_snapshots.player_id` is TEXT — ids are not numeric across sports,
    the same reason `picks.player_id` is."""
    monkeypatch.setattr(
        "sbm.jobs.roster_pull.fetch_roster",
        lambda team_id, *, client, capture=None: [entry(660271, "D10")],
    )
    client = FakeClient()
    pull_rosters(client, stats=FakeStats(), slate=slate_with(game(555, "H", "A")), now=NOW)  # type: ignore[arg-type]
    assert client.rows_for("injury_snapshots")[0]["player_id"] == "660271"


def test_a_doubleheader_pulls_each_team_once(monkeypatch) -> None:
    """Two games, one pair of teams, a 1 req/s throttle — pulling twice would
    double the request count for identical data."""
    pulled: list[int] = []

    def fake(team_id: int, *, client, capture=None):
        pulled.append(team_id)
        return []

    monkeypatch.setattr("sbm.jobs.roster_pull.fetch_roster", fake)
    slate = slate_with(game(555, "H", "A"), game(556, "H", "A"))
    pull_rosters(FakeClient(), stats=FakeStats(), slate=slate, now=NOW)  # type: ignore[arg-type]
    assert pulled == [1, 2]


def test_a_team_not_yet_in_the_teams_table_is_skipped(monkeypatch) -> None:
    """Job A's upsert has not run — there is no `teams.id` to key the row to."""
    monkeypatch.setattr(
        "sbm.jobs.roster_pull.fetch_roster",
        lambda team_id, *, client, capture=None: [entry(1, "D10")],
    )
    slate = Slate(NOW.date(), [game(555, "H", "A")], {"555": 100}, team_ids={})
    assert pull_rosters(FakeClient(), stats=FakeStats(), slate=slate, now=NOW) == 0  # type: ignore[arg-type]


def test_status_falls_back_through_description_then_code(monkeypatch) -> None:
    monkeypatch.setattr(
        "sbm.jobs.roster_pull.fetch_roster",
        lambda team_id, *, client, capture=None: [entry(1, "D10"), entry(2, "RM", "Removed")],
    )
    client = FakeClient()
    pull_rosters(client, stats=FakeStats(), slate=slate_with(game(555, "H", "A")), now=NOW)  # type: ignore[arg-type]
    statuses = {row["player_id"]: row["status"] for row in client.rows_for("injury_snapshots")}
    assert statuses["1"] == "D10" and statuses["2"] == "Removed"
