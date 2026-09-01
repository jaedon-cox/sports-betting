"""Job G — full historical re-run (backend doc §2.4: on-demand / weekly).

Runs `core.backtest.run_backtest`, which walks the games forward
chronologically, refits the calibrator on strictly earlier settled rows at each
fold, and reports CLV, calibration and ROI. It writes nothing: a backtest that
published rows would pollute the live track record with hypothetical picks.

**It is scheduled weekly and on `workflow_dispatch`, never on push** (§2.2:
Actions minutes, and §2.4: workflows never trigger on `pull_request`, which is
what closes the fork-PR secret-leak vector).

**It will return nothing until the system has captured its own line history,
and that is backend doc §7 item 3, not a defect here.** A backtest needs a
bet-time price and a T-5min closing price for the same game from the same book;
no free source of historical Pinnacle closing lines was found, so the only
usable history is what Job A and Job E capture going forward. `run_backtest`
raises on an empty game list rather than reporting a NaN CLV over zero picks,
which is the correct loud failure — a backtest of nothing is not a result.

`fn_backtest_rows` is the sixth Postgres function `db` ships (see `rpc.py` for
the other five); it is flat by design — one row per (game, market, side) with
its open and closing price — so `db` writes a plain join and this module does
the assembly.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta

import numpy as np

from sbm.contracts.feature import AsOf
from sbm.contracts.market import Market, MarketQuote
from sbm.core.backtest import BacktestGame, run_backtest
from sbm.jobs.context import JobContext
from sbm.jobs.pricing import shared_line_value
from sbm.markets import market_registry
from sbm.odds.snapshot import DEVIG_METHOD
from sbm.sports.mlb.vertical import MLBVertical
from sbm.store.client import PostgrestClient

JOB_NAME = "job_g_backtest"

DEFAULT_LOOKBACK_DAYS = 365
BACKTEST_SEED = 20260901
"""Fixed so two runs of the same window are comparable; `run_backtest` threads
it through every Monte-Carlo draw (CLAUDE.md conventions)."""


def run(ctx: JobContext) -> str:
    end = ctx.slate_date
    start = end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    games = load_backtest_games(ctx.client, sport=ctx.config.sport, start=start, end=end)
    report = run_backtest(
        MLBVertical(),
        games,
        markets=market_registry(),
        devig_method=DEVIG_METHOD,
        rng=np.random.default_rng(BACKTEST_SEED),
        n_draws=ctx.config.n_draws,
        edge_threshold=ctx.config.edge_threshold,
        kelly_fraction=ctx.config.kelly_fraction,
    )
    print(report)
    return f"{start}..{end}: backtested {len(games)} games"


def load_backtest_games(
    client: PostgrestClient, *, sport: str, start: date, end: date
) -> list[BacktestGame]:
    """Assemble `BacktestGame`s from captured open/close pairs and final scores.

    `as_of` is the *open* snapshot's capture time, not a pick's lock time: the
    features must be rebuilt at the instant the bet-time price was knowable, and
    tying it to `picks` instead would make the backtest un-runnable for any game
    the live pipeline happened to skip.
    """
    rows = client.rpc(
        "fn_backtest_rows",
        {"p_sport": sport, "p_from": start.isoformat(), "p_to": end.isoformat()},
    )
    grouped: dict[str, list[dict]] = {}
    for row in rows or []:
        grouped.setdefault(str(row["external_game_id"]), []).append(row)
    markets = market_registry()
    return [_game(game_id, group, markets) for game_id, group in grouped.items()]


def _game(game_id: str, rows: list[dict], markets: Mapping[str, Market]) -> BacktestGame:
    """Flat (market, side) rows -> one `BacktestGame`.

    `as_of` comes from `rows[0]`, which is safe by construction rather than by
    luck: `fn_backtest_rows` computes `as_of_utc` as the earliest open capture
    across the game's markets, so every row of a game carries the same value.

    Both sides of a market must resolve to a single line — `core`'s
    `quoted_lines` raises otherwise, and a run line is stored as -1.5/+1.5 (see
    `pricing.shared_line_value`). A market that cannot resolve is dropped rather
    than guessed; a game left with no markets still becomes a `BacktestGame`
    with no quotes, which `quoted_lines` reports as the join failure it is.
    """
    first = rows[0]
    by_market: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_market.setdefault(str(row["market"]), {})[str(row["side"])] = row

    quotes: list[MarketQuote] = []
    closing: list[MarketQuote] = []
    for market_key, sides in by_market.items():
        market = markets.get(market_key)
        if market is None or set(sides) != set(market.sides):
            continue
        opened = shared_line_value(market.sides, {s: _line(r, "open") for s, r in sides.items()})
        closed = shared_line_value(market.sides, {s: _line(r, "close") for s, r in sides.items()})
        if opened is None or closed is None:
            continue
        for side, row in sides.items():
            quotes.append(_quote(market_key, side, opened.line, row, "open"))
            closing.append(_quote(market_key, side, closed.line, row, "close"))

    return BacktestGame(
        game_id=game_id,
        as_of=AsOf(ts=_as_of(first)),
        quotes=tuple(quotes),
        closing_quotes=tuple(closing),
        outcome=np.array(
            [[float(first["home_score"]), float(first["away_score"])]], dtype=np.float64
        ),
    )


def _line(row: dict, phase: str) -> float | None:
    value = row.get(f"{phase}_line")
    return None if value is None else float(value)


def _quote(market: str, side: str, line: float | None, row: dict, phase: str) -> MarketQuote:
    return MarketQuote(
        market=market, side=side, line=line, price_american=int(row[f"{phase}_price_american"])
    )


def _as_of(row: dict) -> datetime:
    return datetime.fromisoformat(str(row["as_of_utc"]))
