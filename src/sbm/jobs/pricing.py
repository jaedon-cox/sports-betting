"""The live edge layer: stored quote + model probability -> one `picks` row.

**Deliberately not `core.backtest.evaluate_game`.** That function is the only
other place doing de-vig -> edge -> Kelly, so it is exactly what this reaches
for — and it is BACKTEST ONLY. It requires a closing quote and raises without
one, which is right there (silently dropping the games with no close would bias
the gate metric) and impossible here: the close lands at T-5min, after Job D
has locked the pick. Fabricating a close to get past the raise would put an
invented number into `pick_settlements.closing_prob` and corrupt CLV silently,
which is strictly worse than the crash. Live CLV is a settlement-time number
that Job F writes, where a postponed game or a missed sweep is a null row.

So this composes `core.pricing`'s three primitives directly — `devig_sides`,
`edge_pct`, `kelly_stake_fraction` — none of which can raise for want of a
close, because none of them ever see one.

**One row per (game, market), favoured side only.** That is the production
grain (`picks` is `UNIQUE(game_id, market, model_run_id)`, backend doc §3.2):
the joint distribution makes the sides complementary, so recording both would
drive average CLV to ~0 mechanically. Ties break on `Market.sides` order, which
is deterministic.

**Below-threshold picks are still written.** `recommended` is a flag on the
row, not a filter applied before it exists — CLV is tracked on all evaluated
games (model doc §7).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sbm.contracts.market import Market
from sbm.core.pricing import devig_sides, edge_pct, kelly_stake_fraction
from sbm.jobs.rpc import LineQuote
from sbm.odds.snapshot.rows import DEVIG_METHOD

MISSING_SIDE = "missing_side"
"""A market quoted on one side only — de-vig needs the complementary pair."""

LINE_MISMATCH = "line_mismatch"
"""The two sides quote numbers that are not one line, so which side is being
priced would be a guess. See `shared_line` for the pair that *is* one line."""

UNSCORED = "unscored"
"""Quoted on both sides but the model produced no probability for one of them.
Should be unreachable — `picks.line_index` only offers a market to the scorer
when both sides are quoted — but a KeyError deep in a slate publish is a much
worse way to find out than a counted skip."""


@dataclass(frozen=True, slots=True)
class SharedLine:
    """The single number both sides of a market are priced against.

    Wrapped rather than returned bare so `None` can mean "these quotes are not
    one line" without colliding with a moneyline's legitimately absent line.
    """

    line: float | None


def shared_line_value(
    sides_order: tuple[str, ...], lines: Mapping[str, float | None]
) -> SharedLine | None:
    """Resolve two per-side numbers into the one line `Market.probability` takes.

    `markets/spread.py` expresses `line` from the HOME team's perspective and
    uses the same number whichever side is queried — home covers when
    `margin_home > -line`, away exactly when it does not. Books quote a spread
    two-sided with opposite signs, and `odds/snapshot/parse.py` records each
    outcome's `point` verbatim (correctly — `line_snapshots` should hold what
    the book actually published), so an MLB run line arrives here as -1.5 on
    the home row and +1.5 on the away row.

    Two numbers that are exact negatives are therefore one line, and the
    home-perspective value is the first side's: `Market.sides` is documented as
    complementary-ordered, home first for the two-sided team markets. This keys
    on the numbers rather than on a market name — a total quotes 8.5 on both
    sides and takes no branch at all — so nothing here learns MLB's product
    names (CLAUDE.md rule 7), and it degrades to a no-op if `line_snapshots`
    ever stores the home-perspective number on both rows.

    Any other disagreement returns None and the market is skipped. Guessing
    would put the wrong number on an append-only `picks` row, and settlement
    replays `Market.probability` against that stored line — so a sign error
    here does not merely mis-price, it mis-grades.
    """
    values = list(dict.fromkeys(lines[side] for side in sides_order))
    if len(values) == 1:
        return SharedLine(values[0])
    if len(values) == 2 and None not in values and values[0] == -values[1]:  # type: ignore[operator]
        return SharedLine(values[0])
    return None


def shared_line(market: Market, quotes: Mapping[str, LineQuote]) -> SharedLine | None:
    """`shared_line_value` over a market's stored quotes."""
    return shared_line_value(market.sides, {side: quotes[side].line for side in market.sides})


@dataclass(frozen=True, slots=True)
class PricedPick:
    """Field-for-field what `store.runs.PickRow` needs, minus the ids."""

    market: str
    side: str
    line: float | None
    raw_model_prob: float
    model_prob: float
    market_fair_prob: float
    devig_method: str
    market_odds_american: int
    edge_pct: float
    kelly_stake_fraction: float
    recommended: bool


@dataclass(frozen=True, slots=True)
class PriceSkipped:
    """Why one (game, market) produced no pick. Counted, never silently dropped."""

    market: str
    reason: str


def price_market(
    market: Market,
    quotes: dict[str, LineQuote],
    model_probs: dict[str, float],
    raw_probs: dict[str, float],
    *,
    edge_threshold: float,
    kelly_fraction: float,
) -> PricedPick | PriceSkipped:
    """Price one market on one game from its stored two-sided quote."""
    if set(quotes) != set(market.sides):
        return PriceSkipped(market.key, MISSING_SIDE)
    resolved = shared_line(market, quotes)
    if resolved is None:
        return PriceSkipped(market.key, LINE_MISMATCH)
    if set(model_probs) != set(market.sides) or set(raw_probs) != set(market.sides):
        return PriceSkipped(market.key, UNSCORED)

    fair, method = _fair_probs(market, quotes)
    edges = {side: edge_pct(model_probs[side], fair[side]) for side in market.sides}
    side = max(market.sides, key=lambda s: edges[s])
    price = quotes[side].price_american
    stake = kelly_stake_fraction(model_probs[side], price, fraction=kelly_fraction)
    return PricedPick(
        market=market.key,
        side=side,
        # The home-perspective number, NOT this side's stored `point`: it is
        # what `picks.line` means, and Job F replays `Market.probability`
        # against it to settle.
        line=resolved.line,
        raw_model_prob=raw_probs[side],
        model_prob=model_probs[side],
        market_fair_prob=fair[side],
        devig_method=method,
        market_odds_american=price,
        edge_pct=edges[side],
        kelly_stake_fraction=stake,
        recommended=edges[side] > edge_threshold and stake > 0.0,
    )


def _fair_probs(market: Market, quotes: dict[str, LineQuote]) -> tuple[dict[str, float], str]:
    """Prefer the fair prob already stored on the snapshot; de-vig only if absent.

    The stored number is the one `pick_settlements.closing_prob` will be
    compared against at settlement — both come from
    `line_snapshots.implied_prob_devigged`, written by `odds/snapshot/` under
    the method locked in `markets.devig_method`. Recomputing it here would be
    the same arithmetic today and a silent CLV artifact the day that method
    changes, since `line_snapshots` is append-only and cannot be back-corrected
    (`core.pricing.devig`'s module docstring: an ordinary moneyline drift moves
    the fair prob 78 bps purely by switching method, and CLV edges live at tens
    of bps).

    The `devig_sides` fallback covers a snapshot written without one — 004
    makes `implied_prob_devigged` and `devig_method` null or non-null together,
    so a row with neither is possible and must still produce a priceable quote
    rather than a skipped market. It carries that row's own method forward when
    there is one and falls back to the locked default only when there is not.
    """
    method = next(iter(quotes.values())).devig_method or DEVIG_METHOD
    stored = {side: quotes[side].implied_prob_devigged for side in market.sides}
    if all(prob is not None for prob in stored.values()):
        return {side: float(prob) for side, prob in stored.items()}, method
    prices = {side: quotes[side].price_american for side in market.sides}
    return devig_sides(prices, method=method), method
