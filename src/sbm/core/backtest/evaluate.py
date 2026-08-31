"""Turning model probabilities plus book prices into one evaluated pick.

This is the edge layer, and the only place a backtest looks at market odds
(A1). Two things it settles:

* **One row per (game, market), for the side the model favours.** That is the
  production grain — `picks` is `UNIQUE(game_id, market, model_run_id)` and
  stores the favoured side only, because the joint distribution makes the sides
  complementary (backend doc §3.2). Recording both sides instead would drive
  average CLV to ~0 mechanically, since one side's price gain is the other's
  loss, and the headline number would measure nothing.
* **Rows are kept whether or not they clear the bet threshold.** CLV is tracked
  on all evaluated games (model doc §7); `recommended` is a flag on the row, not
  a filter applied before the row exists.

Calibrating each side independently does not preserve `p(home) + p(away) == 1`.
That is fine and deliberate: edge, Kelly and CLV all read only the picked side's
number, so nothing downstream depends on the pair summing to one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sbm.contracts.market import Market, MarketQuote
from sbm.core.backtest.calibrate import apply
from sbm.core.backtest.scoring import RawProbs, quoted_lines
from sbm.core.backtest.settlement import settle
from sbm.core.backtest.types import BacktestGame, EvaluatedPick
from sbm.core.calibration import Calibrator
from sbm.core.clv import compute_clv
from sbm.core.pricing import DEFAULT_KELLY_FRACTION, devig_sides, edge_pct, kelly_stake_fraction


def evaluate_game(
    game: BacktestGame,
    raw_probs: RawProbs,
    markets: Mapping[str, Market],
    calibrators: Mapping[str, Calibrator],
    *,
    devig_method: str,
    fold: int,
    edge_threshold: float = 0.0,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
) -> list[EvaluatedPick]:
    """One `EvaluatedPick` per quoted market on this game.

    `devig_method` is required and must be the method locked for this (sport,
    market) — the same one used at open and at close, or the CLV difference is
    part method artifact (`pricing/devig.py`). `edge_threshold` has no doc-given
    value (model doc §7 leaves book limits and execution realities open), so it
    is caller policy and defaults to "any positive edge".

    BACKTEST ONLY — do not reach for this from a live pick job. It requires a
    closing quote and raises without one, which is correct here (a backtest that
    silently drops the games missing a close biases the gate metric) and
    impossible there: the close lands at T-5min, after Job D has already locked
    the pick, so a live caller cannot supply one without fabricating it. CLV is
    a settlement-time number — `pick_settlements.clv_pct`, written by the
    nightly Job F (backend doc §3.2) — not a pick-time one. A live pick path
    composes `pricing`'s `devig_sides`, `edge_pct` and `kelly_stake_fraction`
    directly; none of those ever see a closing quote, so none of them can raise
    for want of one.
    """
    picks: list[EvaluatedPick] = []
    for market_key, line in quoted_lines(game).items():
        market = markets[market_key]
        bet = _prices(game.quotes, market, game.game_id, "bet-time")
        close = _prices(game.closing_quotes, market, game.game_id, "closing")
        bet_fair = devig_sides(bet, method=devig_method)
        close_fair = devig_sides(close, method=devig_method)

        calibrator = calibrators.get(market_key)
        raw = {s: raw_probs[(game.game_id, market_key, s)] for s in market.sides}
        model = {s: apply(calibrator, raw[s]) for s in market.sides}
        edges = {s: edge_pct(model[s], bet_fair[s]) for s in market.sides}

        # market.sides order breaks exact ties deterministically.
        side = max(market.sides, key=lambda s: edges[s])
        stake = kelly_stake_fraction(model[side], bet[side], fraction=kelly_fraction)
        clv = compute_clv(bet_fair[side], close_fair[side])
        picks.append(
            EvaluatedPick(
                game_id=game.game_id,
                market=market_key,
                side=side,
                line=line,
                price_american=bet[side],
                raw_model_prob=raw[side],
                model_prob=model[side],
                market_fair_prob=bet_fair[side],
                closing_prob=close_fair[side],
                closing_line=_closing_line(game.closing_quotes, market_key),
                edge_pct=edges[side],
                kelly_stake_fraction=stake,
                recommended=edges[side] > edge_threshold and stake > 0.0,
                clv_pct=clv.clv_pct,
                clv_bps=clv.clv_bps,
                settlement=settle(market, side, line, game.outcome),
                fold=fold,
            )
        )
    return picks


def _prices(
    quotes: Sequence[MarketQuote], market: Market, game_id: str, label: str
) -> dict[str, int]:
    """Both complementary sides' American prices, in `Market.sides` order.

    De-vig needs the pair; a market quoted on one side only cannot be de-vigged,
    and guessing the missing side would fabricate the fair prob CLV is measured
    against.
    """
    by_side = {q.side: q.price_american for q in quotes if q.market == market.key}
    missing = [s for s in market.sides if s not in by_side]
    if missing:
        raise ValueError(f"{game_id}/{market.key}: no {label} quote for side(s) {missing}")
    return {s: by_side[s] for s in market.sides}


def _closing_line(quotes: Sequence[MarketQuote], market_key: str) -> float | None:
    for quote in quotes:
        if quote.market == market_key:
            return quote.line
    return None
