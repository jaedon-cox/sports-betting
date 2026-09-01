"""The live edge layer. These are the numbers the whole product is graded on."""

from __future__ import annotations

from datetime import UTC, datetime

from sbm.jobs.pricing import (
    LINE_MISMATCH,
    MISSING_SIDE,
    UNSCORED,
    PricedPick,
    PriceSkipped,
    price_market,
)
from sbm.jobs.rpc import LineQuote
from sbm.markets import market_registry

MARKETS = market_registry()
NOW = datetime(2026, 7, 1, 22, 15, tzinfo=UTC)


def quote(side: str, price: int, *, line: float | None = None, fair: float | None = None) -> LineQuote:
    return LineQuote(
        game_id=1,
        market="moneyline" if line is None else "total",
        side=side,
        line=line,
        price_american=price,
        implied_prob_devigged=fair if fair is not None else 0.5,
        devig_method="power",
        captured_at_utc=NOW,
        is_closing=False,
    )


def test_favoured_side_only_one_row_per_market() -> None:
    """`picks` is UNIQUE(game_id, market, model_run_id) and stores the favoured
    side only — recording both would drive average CLV to ~0 mechanically."""
    quotes = {"home": quote("home", -120, fair=0.55), "away": quote("away", 100, fair=0.45)}
    priced = price_market(
        MARKETS["moneyline"],
        quotes,
        model_probs={"home": 0.52, "away": 0.48},
        raw_probs={"home": 0.51, "away": 0.49},
        edge_threshold=0.0,
        kelly_fraction=0.25,
    )
    assert isinstance(priced, PricedPick)
    assert priced.side == "away"  # away edge +0.03 beats home's -0.03
    assert priced.market_fair_prob == 0.45
    assert priced.market_odds_american == 100
    assert round(priced.edge_pct, 10) == 0.03


def test_the_stored_devigged_probability_is_used_not_recomputed() -> None:
    """`pick_settlements.closing_prob` comes from the same column at settlement.
    Recomputing here would be identical today and a silent CLV artifact the day
    `markets.devig_method` changes, since `line_snapshots` is append-only."""
    quotes = {"home": quote("home", -120, fair=0.61), "away": quote("away", 100, fair=0.39)}
    priced = price_market(
        MARKETS["moneyline"], quotes, {"home": 0.7, "away": 0.3}, {"home": 0.7, "away": 0.3},
        edge_threshold=0.0, kelly_fraction=0.25,
    )
    assert isinstance(priced, PricedPick)
    assert priced.market_fair_prob == 0.61  # not the ~0.5238 a power de-vig gives
    assert priced.devig_method == "power"


def test_falls_back_to_devig_when_the_snapshot_stored_no_fair_probability() -> None:
    """004 pairs `implied_prob_devigged` and `devig_method` as null-or-both, so a
    row with neither is possible and must still price rather than be skipped."""
    quotes = {
        "home": LineQuote(1, "moneyline", "home", None, -120, None, None, NOW, False),
        "away": LineQuote(1, "moneyline", "away", None, 100, None, None, NOW, False),
    }
    priced = price_market(
        MARKETS["moneyline"], quotes, {"home": 0.7, "away": 0.3}, {"home": 0.7, "away": 0.3},
        edge_threshold=0.0, kelly_fraction=0.25,
    )
    assert isinstance(priced, PricedPick)
    assert 0.5 < priced.market_fair_prob < 0.6
    assert abs(priced.market_fair_prob - 0.61) > 0.01
    assert priced.devig_method == "power"  # the locked default, since the row carried none


def test_a_one_sided_quote_is_skipped_with_a_reason() -> None:
    priced = price_market(
        MARKETS["moneyline"], {"home": quote("home", -120)}, {"home": 0.6}, {"home": 0.6},
        edge_threshold=0.0, kelly_fraction=0.25,
    )
    assert priced == PriceSkipped("moneyline", MISSING_SIDE)


def test_sides_quoting_different_lines_are_skipped_not_guessed() -> None:
    """A spread is written from the home perspective and shared across sides; a
    sign-flipped away line would silently price the wrong side."""
    quotes = {
        "over": quote("over", -110, line=8.5, fair=0.5),
        "under": quote("under", -110, line=9.0, fair=0.5),
    }
    priced = price_market(
        MARKETS["total"], quotes, {"over": 0.6, "under": 0.4}, {"over": 0.6, "under": 0.4},
        edge_threshold=0.0, kelly_fraction=0.25,
    )
    assert priced == PriceSkipped("total", LINE_MISMATCH)


def test_below_threshold_picks_are_written_but_not_recommended() -> None:
    """CLV is tracked on all evaluated games (model doc §7) — `recommended` is a
    flag on the row, not a filter applied before the row exists."""
    quotes = {"home": quote("home", -120, fair=0.55), "away": quote("away", 100, fair=0.45)}
    priced = price_market(
        MARKETS["moneyline"], quotes, {"home": 0.56, "away": 0.44}, {"home": 0.56, "away": 0.44},
        edge_threshold=0.02, kelly_fraction=0.25,
    )
    assert isinstance(priced, PricedPick)
    assert priced.side == "home" and round(priced.edge_pct, 10) == 0.01
    assert priced.recommended is False


def test_a_zero_stake_is_never_recommended_even_with_a_positive_edge() -> None:
    """Edge is measured against the de-vigged fair price, sizing against the
    price on offer — they can disagree, and Kelly is the binding one."""
    quotes = {"home": quote("home", -400, fair=0.79), "away": quote("away", 300, fair=0.21)}
    priced = price_market(
        MARKETS["moneyline"], quotes, {"home": 0.7955, "away": 0.2045},
        {"home": 0.7955, "away": 0.2045}, edge_threshold=0.0, kelly_fraction=0.25,
    )
    assert isinstance(priced, PricedPick)
    assert priced.edge_pct > 0
    assert priced.kelly_stake_fraction == 0.0
    assert priced.recommended is False


def test_a_market_the_model_did_not_score_is_a_counted_skip_not_a_key_error() -> None:
    """Unreachable by construction, but a KeyError deep inside a slate publish is
    a much worse way to discover a scoring gap than a counted skip."""
    quotes = {"home": quote("home", -120, fair=0.55), "away": quote("away", 100, fair=0.45)}
    priced = price_market(
        MARKETS["moneyline"], quotes, {"home": 0.52}, {"home": 0.51},
        edge_threshold=0.0, kelly_fraction=0.25,
    )
    assert priced == PriceSkipped("moneyline", UNSCORED)


def test_a_run_line_prices_against_the_home_perspective_number() -> None:
    """The stored rows carry -1.5 (home) and +1.5 (away); `markets/spread.py`
    takes one home-perspective line for both sides. Before this resolution every
    run line was skipped as LINE_MISMATCH, and any that got through would have
    been persisted — and later settled — against the wrong number."""
    quotes = {
        "home": quote("home", 130, line=-1.5, fair=0.42),
        "away": quote("away", -150, line=1.5, fair=0.58),
    }
    priced = price_market(
        MARKETS["spread"], quotes, {"home": 0.47, "away": 0.53}, {"home": 0.47, "away": 0.53},
        edge_threshold=0.0, kelly_fraction=0.25,
    )
    assert isinstance(priced, PricedPick)
    assert priced.side == "home"
    assert priced.line == -1.5  # not +1.5, whichever side won the comparison


def test_the_away_side_of_a_run_line_also_stores_the_home_number() -> None:
    """`picks.line` means one thing regardless of side, and Job F replays
    `Market.probability` against it — a sign error mis-grades, not just
    mis-prices."""
    quotes = {
        "home": quote("home", 130, line=-1.5, fair=0.42),
        "away": quote("away", -150, line=1.5, fair=0.58),
    }
    priced = price_market(
        MARKETS["spread"], quotes, {"home": 0.35, "away": 0.65}, {"home": 0.35, "away": 0.65},
        edge_threshold=0.0, kelly_fraction=0.25,
    )
    assert isinstance(priced, PricedPick)
    assert priced.side == "away"
    assert priced.line == -1.5


def test_lines_that_are_not_a_signed_pair_are_still_a_mismatch() -> None:
    """8.5 vs 9.0 is two different totals, not one line seen from two sides."""
    quotes = {
        "over": quote("over", -110, line=8.5, fair=0.5),
        "under": quote("under", -110, line=9.0, fair=0.5),
    }
    assert price_market(
        MARKETS["total"], quotes, {"over": 0.6, "under": 0.4}, {"over": 0.6, "under": 0.4},
        edge_threshold=0.0, kelly_fraction=0.25,
    ) == PriceSkipped("total", LINE_MISMATCH)
