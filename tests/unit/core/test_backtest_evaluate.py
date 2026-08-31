"""backtest/evaluate.py: the edge layer, one row per (game, market).

The grain is the load-bearing decision: recording both complementary sides
would drive average CLV to ~0 mechanically, since one side's price gain is the
other's loss.
"""

from __future__ import annotations

import numpy as np
import pytest
from conftest import make_game
from numpy.random import default_rng

from sbm.core.backtest import evaluate_game, raw_probabilities
from sbm.core.clv import compute_clv
from sbm.core.pricing import devig_sides

METHOD = "power"


def _evaluate(game, vertical, markets, calibrators=None, **kwargs):
    probs = raw_probabilities(vertical, markets, [game], n_draws=20000, rng=default_rng(5))
    return evaluate_game(
        game, probs, markets, calibrators or {}, devig_method=METHOD, fold=0, **kwargs
    )


def test_one_pick_per_market(vertical, markets: dict) -> None:
    picks = _evaluate(make_game("g020"), vertical, markets)
    assert len(picks) == 1
    assert picks[0].market == "moneyline"
    assert picks[0].side in ("home", "away")


def test_the_favoured_side_is_the_one_with_the_highest_edge(vertical, markets: dict) -> None:
    """`g020` is the fake vertical's strongest home team (P(home) ~ 0.69);
    priced as a modest favourite, the model should want the home side."""
    game = make_game("g020", bet={"home": -130, "away": 115}, close={"home": -140, "away": 120})
    assert _evaluate(game, vertical, markets)[0].side == "home"


def test_market_fair_prob_is_the_devigged_bet_time_price(vertical, markets: dict) -> None:
    game = make_game("g020")
    pick = _evaluate(game, vertical, markets)[0]
    fair = devig_sides({"home": -150, "away": 130}, method=METHOD)
    assert pick.market_fair_prob == pytest.approx(fair[pick.side])
    assert pick.edge_pct == pytest.approx(pick.model_prob - pick.market_fair_prob)


def test_clv_compares_the_same_side_at_both_timestamps(vertical, markets: dict) -> None:
    game = make_game("g020")
    pick = _evaluate(game, vertical, markets)[0]
    closing = devig_sides({"home": -170, "away": 145}, method=METHOD)
    expected = compute_clv(pick.market_fair_prob, closing[pick.side])
    assert pick.closing_prob == pytest.approx(closing[pick.side])
    assert pick.clv_pct == pytest.approx(expected.clv_pct)
    assert pick.clv_bps == pytest.approx(expected.clv_bps)


def test_uncalibrated_pick_keeps_raw_and_model_prob_equal(vertical, markets: dict) -> None:
    """Before a calibrator exists both columns are the same number — and both
    are still persisted, because `raw_model_prob` is the drift signal."""
    pick = _evaluate(make_game("g020"), vertical, markets)[0]
    assert pick.model_prob == pick.raw_model_prob


def test_calibration_moves_model_prob_but_not_raw(vertical, markets: dict) -> None:
    from sbm.core.calibration import IsotonicCalibrator

    raw = np.linspace(0.05, 0.95, 200)
    shrinking = IsotonicCalibrator.fit(raw, (raw > 0.5).astype(float) * 0.5 + 0.25)
    pick = _evaluate(make_game("g020"), vertical, markets, {"moneyline": shrinking})[0]
    assert pick.model_prob != pick.raw_model_prob
    assert 0.0 <= pick.model_prob <= 1.0


def test_rows_are_kept_when_the_edge_does_not_clear_the_threshold(
    vertical, markets: dict
) -> None:
    """CLV is tracked on all evaluated games (model doc §7): `recommended` is a
    flag on the row, never a filter applied before the row exists."""
    picks = _evaluate(make_game("g020"), vertical, markets, edge_threshold=0.99)
    assert len(picks) == 1
    assert picks[0].recommended is False
    assert np.isfinite(picks[0].clv_pct)


def test_a_positive_edge_the_vig_eats_is_not_a_bet(vertical, markets: dict) -> None:
    """Edge is measured against the de-vigged fair price, Kelly against the
    price actually on offer. A -140/-140 book de-vigs to 50/50, so a 0.566 model
    prob shows a real edge — but you are laying 1.4 to win 1, and the stake is
    correctly zero. `recommended` must respect the stake, not just the edge.
    """
    game = make_game("g015", bet={"home": -140, "away": -140}, close={"home": -140, "away": -140})
    pick = _evaluate(game, vertical, markets)[0]
    assert pick.edge_pct > 0.0
    assert pick.kelly_stake_fraction == 0.0
    assert pick.recommended is False


def test_settlement_and_line_are_recorded(vertical, markets: dict) -> None:
    game = make_game("g020", outcome=(5.0, 3.0))
    pick = _evaluate(game, vertical, markets)[0]
    assert pick.settlement == ("win" if pick.side == "home" else "loss")
    assert pick.line is None
    assert pick.fold == 0


def test_line_movement_is_recorded_as_an_open_close_pair(vertical, markets: dict) -> None:
    """Two snapshots per game, so line movement is a pair, not a curve
    (backend doc §5)."""
    game = make_game(
        "g020",
        market="total",
        line=8.5,
        bet={"over": -110, "under": -110},
        close={"over": -105, "under": -115},
    )
    game = type(game)(
        game_id=game.game_id,
        as_of=game.as_of,
        quotes=game.quotes,
        closing_quotes=tuple(
            type(q)(market=q.market, side=q.side, line=9.0, price_american=q.price_american)
            for q in game.closing_quotes
        ),
        outcome=game.outcome,
    )
    pick = _evaluate(game, vertical, markets)[0]
    assert (pick.line, pick.closing_line) == (8.5, 9.0)


def test_a_missing_closing_quote_is_an_error(vertical, markets: dict) -> None:
    """CLV is the gate metric; silently dropping the games without a close
    would bias exactly the number we are gating on."""
    game = make_game("g020")
    game = type(game)(
        game_id=game.game_id,
        as_of=game.as_of,
        quotes=game.quotes,
        closing_quotes=game.closing_quotes[:1],
        outcome=game.outcome,
    )
    with pytest.raises(ValueError, match="no closing quote"):
        _evaluate(game, vertical, markets)


def test_a_one_sided_bet_time_quote_is_an_error(vertical, markets: dict) -> None:
    """De-vig needs the complementary pair; inventing the missing side would
    fabricate the fair prob CLV is measured against."""
    game = make_game("g020")
    game = type(game)(
        game_id=game.game_id,
        as_of=game.as_of,
        quotes=game.quotes[:1],
        closing_quotes=game.closing_quotes,
        outcome=game.outcome,
    )
    with pytest.raises(ValueError, match="no bet-time quote"):
        _evaluate(game, vertical, markets)
