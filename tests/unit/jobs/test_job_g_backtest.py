"""Job G's assembly step: flat (game, market, side) rows -> `BacktestGame`s.

`fn_backtest_rows` is deliberately flat — one row per side with its open and
closing price — so all of the joining happens here. What is worth pinning is
which rows get *dropped*: a backtest that quietly keeps a half-resolved market
reports a CLV number computed against a line nobody was ever quoted.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sbm.jobs.job_g_backtest import load_backtest_games
from tests.unit.jobs.fakes import FakeClient

AS_OF = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def row(
    *,
    game: str = "555",
    market: str = "moneyline",
    side: str = "home",
    open_line: float | None = None,
    open_price: int = -120,
    close_line: float | None = None,
    close_price: int = -130,
    home_score: int = 5,
    away_score: int = 3,
) -> dict:
    return {
        "external_game_id": game,
        "game_date": "2026-07-01",
        "as_of_utc": AS_OF.isoformat(),
        "market": market,
        "side": side,
        "open_line": open_line,
        "open_price_american": open_price,
        "close_line": close_line,
        "close_price_american": close_price,
        "home_score": home_score,
        "away_score": away_score,
    }


def moneyline(game: str = "555") -> list[dict]:
    return [
        row(game=game, side="home", open_price=-120, close_price=-130),
        row(game=game, side="away", open_price=100, close_price=110),
    ]


def total(game: str = "555", *, open_line: float = 8.5, close_line: float = 8.5) -> list[dict]:
    return [
        row(game=game, market="total", side=s, open_line=open_line, close_line=close_line)
        for s in ("over", "under")
    ]


def load(rows: list[dict]):
    client = FakeClient(rpc_results={"fn_backtest_rows": rows})
    return load_backtest_games(
        client, sport="mlb", start=date(2026, 6, 1), end=date(2026, 7, 1)  # type: ignore[arg-type]
    )


def test_rows_are_grouped_into_one_game_each_with_both_price_phases() -> None:
    games = load(moneyline())
    assert len(games) == 1
    assert {(q.market, q.side, q.price_american) for q in games[0].quotes} == {
        ("moneyline", "home", -120), ("moneyline", "away", 100)
    }
    assert {(q.side, q.price_american) for q in games[0].closing_quotes} == {
        ("home", -130), ("away", 110)
    }


def test_as_of_is_the_open_capture_instant_not_a_pick_lock() -> None:
    """Features must be rebuilt at the instant the bet-time price was knowable;
    tying it to `picks` would make the backtest un-runnable for any game the
    live pipeline skipped."""
    assert load(moneyline())[0].as_of.ts == AS_OF


def test_the_realized_outcome_is_the_two_column_home_away_pair() -> None:
    game = load(moneyline())[0]
    assert game.outcome.shape == (1, 2)
    assert game.outcome.tolist() == [[5.0, 3.0]]


def test_multiple_games_become_multiple_backtest_games() -> None:
    games = load(moneyline("555") + moneyline("556"))
    assert sorted(g.game_id for g in games) == ["555", "556"]


def test_a_market_quoted_on_one_side_only_is_dropped() -> None:
    """It cannot be de-vigged, and half a market is not a price."""
    games = load(moneyline() + [row(market="total", side="over", open_line=8.5, close_line=8.5)])
    assert {q.market for q in games[0].quotes} == {"moneyline"}


def test_a_market_whose_two_sides_disagree_on_the_line_is_dropped() -> None:
    """`core`'s `quoted_lines` raises on an ambiguous line; dropping it here
    keeps one bad market from failing the whole backtest."""
    rows = moneyline() + [
        row(market="total", side="over", open_line=8.5, close_line=8.5),
        row(market="total", side="under", open_line=9.0, close_line=8.5),
    ]
    assert {q.market for q in load(rows)[0].quotes} == {"moneyline"}


def test_a_run_line_resolves_from_its_mirrored_pair() -> None:
    """A run line is stored as -1.5/+1.5, not as one shared number."""
    rows = [
        row(market="spread", side="home", open_line=-1.5, close_line=-1.5),
        row(market="spread", side="away", open_line=1.5, close_line=1.5),
    ]
    games = load(rows)
    assert {q.market for q in games[0].quotes} == {"spread"}
    assert {q.line for q in games[0].quotes} == {-1.5}


def test_a_market_this_repo_does_not_price_is_dropped_not_guessed() -> None:
    rows = moneyline() + [
        row(market="first_inning_nrfi", side="yes"),
        row(market="first_inning_nrfi", side="no"),
    ]
    assert {q.market for q in load(rows)[0].quotes} == {"moneyline"}


def test_open_and_close_lines_are_resolved_independently_so_movement_survives() -> None:
    """A total that opened 8.5 and closed 9.0 is the ordinary case, and it is the
    whole signal: collapsing the two phases onto one line would price the bet
    against a number it was never taken at."""
    rows = total(open_line=8.5, close_line=9.0)
    game = load(rows)[0]
    assert {q.line for q in game.quotes} == {8.5}
    assert {q.line for q in game.closing_quotes} == {9.0}


def test_a_moneyline_carries_no_line_in_either_phase() -> None:
    """`line_snapshots.line` is NULL for moneyline by design; that is a real
    resolved value, not a failure to resolve."""
    game = load(moneyline())[0]
    assert {q.line for q in game.quotes} == {None}
    assert {q.line for q in game.closing_quotes} == {None}


def test_a_game_left_with_no_usable_market_still_becomes_a_game() -> None:
    """`quoted_lines` then reports the join failure it is, rather than the game
    vanishing from the run count."""
    games = load([row(market="total", side="over", open_line=8.5, close_line=8.5)])
    assert len(games) == 1 and games[0].quotes == ()


def test_an_empty_result_set_loads_nothing_rather_than_raising() -> None:
    """`run_backtest` is what raises on an empty game list — a backtest of
    nothing is not a result, but that judgement is not this function's."""
    assert load([]) == []


def test_the_window_is_passed_through_to_the_function_as_dates() -> None:
    client = FakeClient(rpc_results={"fn_backtest_rows": []})
    load_backtest_games(client, sport="mlb", start=date(2025, 9, 1), end=date(2026, 7, 1))  # type: ignore[arg-type]
    name, params = client.rpcs[0]
    assert name == "fn_backtest_rows"
    assert params == {"p_sport": "mlb", "p_from": "2025-09-01", "p_to": "2026-07-01"}
