"""Both resolvers are pure functions over ScheduledGame — no network.

The external/internal split is the point: `odds/snapshot/` writes db's
internal `games.id` (int), which schedule data alone cannot produce.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sbm.sports.mlb.ingest.statsapi.schedule import ProbablePitcher, ScheduledGame
from sbm.odds.resolution import (
    DOUBLEHEADER,
    NOT_INGESTED,
    OFF_SLATE,
    ResolvedExternalId,
    ResolvedGameId,
    Unresolved,
)
from sbm.sports.mlb.ingest.statsapi.teams import (
    build_external_game_id_resolver,
    compose_internal_resolver,
)

_NO_PITCHER = ProbablePitcher(player_id=None, full_name=None)


def _game(game_pk: int, home: str, away: str) -> ScheduledGame:
    return ScheduledGame(
        game_pk=game_pk,
        game_date=None,
        start_time_utc=None,
        status="scheduled",
        home_team_id=None,
        home_team_name=home,
        away_team_id=None,
        away_team_name=away,
        venue_id=None,
        venue_name=None,
        home_probable_pitcher=_NO_PITCHER,
        away_probable_pitcher=_NO_PITCHER,
        home_score=None,
        away_score=None,
    )


def test_resolves_a_unique_team_pair() -> None:
    resolve = build_external_game_id_resolver([_game(1, "New York Yankees", "Boston Red Sox")])
    assert resolve("New York Yankees", "Boston Red Sox", datetime.now(UTC)) == ResolvedExternalId("1")


def test_unknown_team_pair_is_off_slate_not_a_failure() -> None:
    """The odds feed spans a wider window than the one date this index
    covers, so a pair we don't have is routine — see odds/resolution.py."""
    resolve = build_external_game_id_resolver([_game(1, "New York Yankees", "Boston Red Sox")])
    result = resolve("Some Team", "Other Team", datetime.now(UTC))
    assert result == Unresolved(OFF_SLATE, "Some Team", "Other Team")


def test_doubleheader_collision_reports_why_rather_than_guessing() -> None:
    resolve = build_external_game_id_resolver(
        [
            _game(1, "New York Yankees", "Boston Red Sox"),
            _game(2, "New York Yankees", "Boston Red Sox"),
        ]
    )
    result = resolve("New York Yankees", "Boston Red Sox", datetime.now(UTC))
    assert isinstance(result, Unresolved)
    assert result.reason == DOUBLEHEADER


def test_compose_maps_external_gamepk_to_internal_games_id() -> None:
    external = build_external_game_id_resolver([_game(1, "New York Yankees", "Boston Red Sox")])
    resolve = compose_internal_resolver(external, {"1": 4242})
    result = resolve("New York Yankees", "Boston Red Sox", datetime.now(UTC))
    assert result == ResolvedGameId(4242)
    assert isinstance(result.game_id, int)


def test_compose_flags_a_game_not_yet_upserted_as_not_ingested() -> None:
    """The one reason that signals something upstream is actually wrong,
    so it must stay distinguishable from the two routine ones."""
    external = build_external_game_id_resolver([_game(1, "New York Yankees", "Boston Red Sox")])
    resolve = compose_internal_resolver(external, {})
    result = resolve("New York Yankees", "Boston Red Sox", datetime.now(UTC))
    assert isinstance(result, Unresolved)
    assert result.reason == NOT_INGESTED


def test_compose_propagates_the_upstream_reason_unchanged() -> None:
    """A doubleheader must not be relabelled NOT_INGESTED on the way through —
    they call for opposite responses."""
    external = build_external_game_id_resolver(
        [
            _game(1, "New York Yankees", "Boston Red Sox"),
            _game(2, "New York Yankees", "Boston Red Sox"),
        ]
    )
    resolve = compose_internal_resolver(external, {"1": 4242, "2": 4243})
    result = resolve("New York Yankees", "Boston Red Sox", datetime.now(UTC))
    assert isinstance(result, Unresolved)
    assert result.reason == DOUBLEHEADER


def test_no_resolver_outcome_is_ever_none() -> None:
    """`core`'s audit finding, pinned at the resolution site itself."""
    external = build_external_game_id_resolver([_game(1, "New York Yankees", "Boston Red Sox")])
    resolve = compose_internal_resolver(external, {})
    for pair in [("New York Yankees", "Boston Red Sox"), ("Nobody", "Nobody Else")]:
        assert resolve(*pair, datetime.now(UTC)) is not None
