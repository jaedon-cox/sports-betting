"""Id translation, quote indexing, slate rows, and the closing window."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sbm.jobs.job_e_closing_lines import closing_window_games
from sbm.jobs.picks import index_quotes, line_index, resolve_model_version, to_pick_row
from sbm.jobs.pricing import PricedPick
from sbm.jobs.rpc import LineQuote
from sbm.jobs.slate import write_slate_status
from sbm.markets import market_registry
from sbm.jobs.slate_ingest import _game_row
from tests.unit.jobs.fakes import FakeClient
from tests.unit.jobs.test_odds_sweep import game, make_slate

NOW = datetime(2026, 7, 1, 22, 45, tzinfo=UTC)


def quote(game_id: int, market: str, side: str, line: float | None = None) -> LineQuote:
    return LineQuote(game_id, market, side, line, -110, 0.5, "power", NOW, False)


def test_quotes_are_reindexed_from_internal_ids_onto_external_ones() -> None:
    """`line_snapshots.game_id` is the Postgres surrogate; `features/` only ever
    sees the gamePk (CLAUDE.md's cross-layer id rule)."""
    index = index_quotes(
        [quote(101, "moneyline", "home"), quote(101, "moneyline", "away")], {101: "1"}
    )
    assert set(index) == {"1"}
    assert set(index["1"]["moneyline"]) == {"home", "away"}


def test_a_quote_for_a_game_off_this_slate_is_dropped_not_mis_keyed() -> None:
    assert index_quotes([quote(999, "moneyline", "home")], {101: "1"}) == {}


def test_one_sided_markets_are_left_out_of_the_scoring_line_index() -> None:
    """They cannot be de-vigged, so scoring them would spend Monte-Carlo draws
    on a pick `pricing.py` will skip anyway."""
    index = index_quotes(
        [
            quote(101, "total", "over", 8.5),
            quote(101, "total", "under", 8.5),
            quote(101, "moneyline", "home"),
        ],
        {101: "1"},
    )
    assert line_index(index, market_registry()) == {("1", "total"): 8.5}


def test_pick_rows_carry_the_internal_id_and_the_lock_instant() -> None:
    priced = PricedPick("total", "over", 8.5, 0.54, 0.55, 0.52, "power", -105, 0.03, 0.01, True)
    row = to_pick_row(priced, game_id=101, game_date=date(2026, 7, 1), locked_at=NOW)
    assert (row.game_id, row.line, row.pick_locked_at) == (101, 8.5, NOW)
    assert (row.player_id, row.stat_type) == (None, None)  # team market, per fn_validate_pick
    assert row.book == "pinnacle"  # book consistency (§5) — same book at open and close


def test_model_version_is_upserted_on_the_git_sha() -> None:
    client = FakeClient()
    assert resolve_model_version(client, sport="mlb", git_sha="abc123") == 1  # type: ignore[arg-type]
    table, rows, on_conflict = client.upserts[0]
    assert (table, on_conflict) == ("model_versions", "sport,git_sha")
    assert rows[0] == {"sport": "mlb", "git_sha": "abc123"}


def test_slate_status_upserts_on_the_slate_key() -> None:
    client = FakeClient()
    write_slate_status(
        client,  # type: ignore[arg-type]
        sport="mlb", slate_date=date(2026, 7, 1), status="published", n_games=15, model_run_id=7,
    )
    table, rows, on_conflict = client.upserts[0]
    assert (table, on_conflict) == ("slate_status", "sport,slate_date")
    assert rows[0]["status"] == "published" and rows[0]["model_run_id"] == 7


def test_a_write_without_a_run_id_clears_it_rather_than_omitting_it() -> None:
    """PostgREST upsert is merge-duplicates, so an omitted column keeps the old
    value: a `pending` write after a `published` one would flip the status while
    leaving the stale run id attached, and the frontend would show a publish time
    for a slate this table calls unpublished."""
    client = FakeClient()
    write_slate_status(
        client, sport="mlb", slate_date=date(2026, 7, 1), status="pending", n_games=15  # type: ignore[arg-type]
    )
    assert client.upserts[0][1][0]["model_run_id"] is None


def test_a_game_with_an_unknown_team_yields_no_row_rather_than_raising() -> None:
    """One malformed game must not drop the whole slate — the failure mode every
    parse in `ingest` is written to avoid."""
    assert _game_row(game(1, "Yankees", "Red Sox"), "mlb", {}) is None
    row = _game_row(game(1, "Yankees", "Red Sox"), "mlb", {1: 11, 2: 22})
    assert row is not None
    assert (row.external_game_id, row.home_team_id, row.away_team_id) == ("1", 11, 22)


def test_the_closing_window_is_t_minus_20_to_t_minus_1() -> None:
    """Sweeping after first pitch would capture an in-play price and quietly
    corrupt every CLV number it touched."""
    slate = make_slate([game(1, "A", "B", start_hour=23)])  # 23:05 UTC
    assert closing_window_games(slate, datetime(2026, 7, 1, 22, 50, tzinfo=UTC)) == {"1"}
    assert closing_window_games(slate, datetime(2026, 7, 1, 22, 40, tzinfo=UTC)) == frozenset()
    assert closing_window_games(slate, datetime(2026, 7, 1, 23, 5, tzinfo=UTC)) == frozenset()
    assert closing_window_games(slate, datetime(2026, 7, 1, 23, 30, tzinfo=UTC)) == frozenset()


def test_a_game_with_no_known_start_is_never_assumed_imminent() -> None:
    without_start = game(1, "A", "B")
    slate = make_slate([type(without_start)(**{**{f: getattr(without_start, f) for f in without_start.__slots__}, "start_time_utc": None})])
    assert closing_window_games(slate, NOW) == frozenset()


def test_devig_method_always_travels_with_the_fair_probability() -> None:
    """`picks` carries CHECK ((market_fair_prob IS NULL) = (devig_method IS
    NULL)) and `PickRow.__post_init__` mirrors it — omitting the method would
    roll back the whole slate's publish transaction in Postgres instead of
    failing on one row here."""
    priced = PricedPick("moneyline", "home", None, 0.55, 0.56, 0.52, "power", -120, 0.04, 0.02, True)
    row = to_pick_row(priced, game_id=101, game_date=date(2026, 7, 1), locked_at=NOW)
    assert row.devig_method == "power"
    assert row.market_fair_prob == 0.52


def test_the_run_lines_two_signed_points_resolve_to_one_home_perspective_line() -> None:
    """`odds/snapshot/parse.py` stores each outcome's own `point`, so a run line
    lands as -1.5 on the home row and +1.5 on the away row. `markets/spread.py`
    takes ONE home-perspective number for both sides, so the pair must collapse
    to -1.5 — handing +1.5 to `SpreadMarket.probability` prices the opposite
    side without raising."""
    index = index_quotes(
        [quote(101, "spread", "home", -1.5), quote(101, "spread", "away", 1.5)], {101: "1"}
    )
    assert line_index(index, market_registry()) == {("1", "spread"): -1.5}


def test_the_resolution_is_order_independent() -> None:
    """Dict order must not decide which sign is persisted."""
    reversed_order = index_quotes(
        [quote(101, "spread", "away", 1.5), quote(101, "spread", "home", -1.5)], {101: "1"}
    )
    assert line_index(reversed_order, market_registry()) == {("1", "spread"): -1.5}


def test_a_home_underdog_run_line_keeps_its_positive_sign() -> None:
    index = index_quotes(
        [quote(101, "spread", "home", 1.5), quote(101, "spread", "away", -1.5)], {101: "1"}
    )
    assert line_index(index, market_registry()) == {("1", "spread"): 1.5}
