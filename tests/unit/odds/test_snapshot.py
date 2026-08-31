"""odds/snapshot/ normalizes Odds API payloads into line_snapshots rows.

De-vig and game-id resolution are injected fakes here so these tests exercise
normalization alone. `core.pricing.devig.devig_sides` is now the package's
real default; the resolver stays injected because it needs a games lookup
this layer doesn't own (see `odds/resolution.py`).

The persisted market key for MLB's run line is `spread`, not `run_line` —
it is `markets/spread.py` with line=+/-1.5. Adjudicated by `main`: shared
code must not learn MLB's product names (CLAUDE.md rule 7), and
`db/migrations/003_picks.sql` deliberately left the market column un-enum'd
so props and other sports aren't blocked.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sbm.odds.resolution import (
    NO_PINNACLE_BOOK,
    OFF_SLATE,
    GameIdResolution,
    ResolvedGameId,
    Unresolved,
)
from sbm.odds.snapshot import normalize_snapshot

CAPTURED_AT = datetime(2026, 8, 29, 23, 0, tzinfo=UTC)


def fake_devig(prices_by_side: dict[str, int], *, method: str) -> dict[str, float]:
    """No-vig midpoint stand-in — real math belongs to `core.pricing`.

    Keyword-only `method` mirrors the `DevigFn` protocol `snapshot/rows.py` declares.
    """
    del method
    return dict.fromkeys(prices_by_side, 1 / len(prices_by_side))


def fake_resolver(home: str, away: str, commence: datetime) -> GameIdResolution:
    """Stands in for db's internal `games.id` — an int, not the StatsAPI gamePk.

    Returns the `Resolved…`/`Unresolved` pair rather than `int | None`, so a
    miss carries a reason and can never reach a query filter as a `None`.
    """
    del commence
    known = {("New York Yankees", "Boston Red Sox"): 101}
    internal = known.get((home, away))
    if internal is None:
        return Unresolved(OFF_SLATE, home, away)
    return ResolvedGameId(internal)


def _game(**overrides: object) -> dict:
    base = {
        "id": "odds-api-abc123",
        "commence_time": "2026-08-29T23:05:00Z",
        "home_team": "New York Yankees",
        "away_team": "Boston Red Sox",
        "bookmakers": [
            {
                "key": "pinnacle",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "New York Yankees", "price": -150},
                            {"name": "Boston Red Sox", "price": 130},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "price": -110, "point": 8.5},
                            {"name": "Under", "price": -110, "point": 8.5},
                        ],
                    },
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "New York Yankees", "price": -110, "point": -1.5},
                            {"name": "Boston Red Sox", "price": -110, "point": 1.5},
                        ],
                    },
                ],
            }
        ],
    }
    base.update(overrides)
    return base


def test_normalize_produces_one_row_pair_per_market() -> None:
    rows = normalize_snapshot(
        [_game()],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
    ).rows
    by_market = {}
    for row in rows:
        by_market.setdefault(row.market, []).append(row)
    assert set(by_market) == {"moneyline", "total", "spread"}
    assert {r.side for r in by_market["moneyline"]} == {"home", "away"}
    assert {r.side for r in by_market["total"]} == {"over", "under"}
    assert {r.side for r in by_market["spread"]} == {"home", "away"}


def test_moneyline_row_carries_no_line_and_correct_price() -> None:
    rows = normalize_snapshot(
        [_game()],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=True,
    ).rows
    home_ml = next(r for r in rows if r.market == "moneyline" and r.side == "home")
    assert home_ml.line is None
    assert home_ml.price_american == -150
    assert home_ml.game_id == 101
    assert home_ml.is_closing is True
    assert home_ml.source == "pinnacle"
    assert home_ml.implied_prob_devigged == 0.5


def test_total_row_carries_the_point_as_line() -> None:
    rows = normalize_snapshot(
        [_game()],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
    ).rows
    over = next(r for r in rows if r.market == "total" and r.side == "over")
    assert over.line == 8.5


def test_spread_row_carries_the_signed_run_line_as_line() -> None:
    """MLB's run line rides the generic `spread` market key (module docstring)."""
    rows = normalize_snapshot(
        [_game()],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
    ).rows
    home_spread = next(r for r in rows if r.market == "spread" and r.side == "home")
    assert home_spread.line == -1.5


def test_game_with_no_pinnacle_book_is_skipped_not_raised() -> None:
    game = _game(bookmakers=[{"key": "draftkings", "markets": []}])
    result = normalize_snapshot(
        [game],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
    )
    assert result.rows == []
    assert result.skipped_by_reason == {NO_PINNACLE_BOOK: 1}


def test_unresolvable_game_is_skipped_not_raised() -> None:
    game = _game(home_team="Some Unknown Team")
    result = normalize_snapshot(
        [game],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
    )
    assert result.rows == []
    assert result.skipped_by_reason == {OFF_SLATE: 1}


def test_malformed_market_with_one_outcome_is_skipped_defensively() -> None:
    game = _game()
    game["bookmakers"][0]["markets"][0]["outcomes"] = [
        {"name": "New York Yankees", "price": -150}
    ]
    rows = normalize_snapshot(
        [game],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
    ).rows
    assert not any(r.market == "moneyline" for r in rows)


def test_row_carries_the_devig_method_that_produced_its_probability() -> None:
    """004 constrains implied_prob_devigged and devig_method to be null or
    non-null together, and line_snapshots is append-only — so the method has
    to ride with the number, not be re-derived from config at write time."""
    rows = normalize_snapshot(
        [_game()],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
    ).rows
    assert {r.devig_method for r in rows} == {"power"}
    assert all(r.implied_prob_devigged is not None for r in rows)


def test_a_non_default_method_is_carried_through_not_overwritten() -> None:
    rows = normalize_snapshot(
        [_game()],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
        method="shin",
    ).rows
    assert {r.devig_method for r in rows} == {"shin"}


def test_rows_map_onto_dbs_writer_row_without_violating_its_check() -> None:
    """The pairing db's __post_init__ enforces is exactly what this module
    must not emit half of — pin the mapping, not just the field's presence."""
    from sbm.store.snapshots import LineSnapshotRow as DbRow

    row = normalize_snapshot(
        [_game()],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
    ).rows[0]
    db_row = DbRow(
        game_id=row.game_id,
        sport="mlb",
        market=row.market,
        side=row.side,
        line=row.line,
        price_american=row.price_american,
        implied_prob_devigged=row.implied_prob_devigged,
        devig_method=row.devig_method,
        captured_at_utc=row.captured_at_utc,
        is_closing=row.is_closing,
        source=row.source,
    )
    assert db_row.devig_method == "power"


def test_a_clean_slate_reports_no_skips() -> None:
    result = normalize_snapshot(
        [_game()],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
    )
    assert result.skipped == []
    assert result.skipped_by_reason == {}


def test_skips_are_counted_by_reason_so_routine_differs_from_systemic() -> None:
    """The whole point of keeping reasons: three skipped doubleheaders and a
    dead schedule ingest both produce zero rows, and only the counts tell
    them apart (odds/resolution.py)."""
    result = normalize_snapshot(
        [
            _game(),
            _game(home_team="Some Unknown Team"),
            _game(away_team="Another Unknown Team"),
            _game(bookmakers=[{"key": "draftkings", "markets": []}]),
        ],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
    )
    assert result.skipped_by_reason == {OFF_SLATE: 2, NO_PINNACLE_BOOK: 1}
    assert {s.home_team for s in result.skipped} >= {"Some Unknown Team"}
    assert len(result.rows) == 6  # the one good game, 3 markets x 2 sides


def test_no_resolution_outcome_can_reach_a_row_as_none() -> None:
    """`core`'s audit finding: a None in a query filter is how a join
    silently returns nothing. There is no longer an Optional to leak."""
    result = normalize_snapshot(
        [_game(), _game(home_team="Some Unknown Team")],
        devig=fake_devig,
        resolve_game_id=fake_resolver,
        captured_at_utc=CAPTURED_AT,
        is_closing=False,
    )
    assert all(isinstance(r.game_id, int) for r in result.rows)
    assert all(r.game_id is not None for r in result.rows)
