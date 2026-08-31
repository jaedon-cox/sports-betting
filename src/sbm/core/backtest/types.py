"""Row shapes a backtest consumes and produces.

`EvaluatedPick`'s field names deliberately mirror `picks` + `pick_settlements`
(backend doc §3.2) so a backtested row and a production row are the *same*
record. If the two shapes drift, backtest CLV stops being a prediction of live
CLV and becomes a number about a system that never ran.
"""

from __future__ import annotations

from dataclasses import dataclass

from sbm.contracts.distribution import Draws
from sbm.contracts.feature import AsOf
from sbm.contracts.market import MarketQuote


@dataclass(frozen=True, slots=True)
class BacktestGame:
    """One settled historical game: when it could be priced, at what, and how
    it finished."""

    game_id: str

    as_of: AsOf
    """Pick-lock instant. Features are rebuilt at exactly this timestamp, so the
    backtest can never see a snapshot the live run wouldn't have had (rule 4).
    Also the chronological sort key for the walk-forward split."""

    quotes: tuple[MarketQuote, ...]
    """Bet-time prices. BOTH sides of every market to be evaluated must be
    present — de-vig needs the complementary pair (`pricing/devig.py`)."""

    closing_quotes: tuple[MarketQuote, ...]
    """The T-5min Pinnacle close, same shape (model doc §7). Must be the same
    book as `quotes` or CLV is not apples-to-apples (backend doc §5)."""

    outcome: Draws
    """The realized result in `Distribution.sample` column layout, shape
    (1, n_dims): (home, away) for team markets, one stat value for a prop.
    Settlement replays the market plugin over this row, so no market carries
    its own settlement branch (`settlement.py`)."""


@dataclass(frozen=True, slots=True)
class EvaluatedPick:
    """One (game, market) evaluation — recorded whether or not it was bet.

    CLV is tracked on all evaluated games, not just placed bets (model doc §7),
    which is why `recommended` is a flag on the row rather than a filter
    applied before the row exists.
    """

    game_id: str
    market: str
    side: str
    line: float | None
    price_american: int

    raw_model_prob: float
    """Pre-calibration market probability — kept for drift monitoring, never
    used for sizing (backend doc §3.2)."""
    model_prob: float
    """Post-calibration; equals `raw_model_prob` when the fold had too little
    settled history to fit a calibrator."""

    market_fair_prob: float
    """De-vigged Pinnacle fair prob for this side at bet time — `bet_prob` in
    `pick_settlements`."""
    closing_prob: float
    """De-vigged fair prob for the same side at the close."""
    closing_line: float | None
    """The close's line for this market; differs from `line` when the number
    moved. Open->close is a pair, not a curve (backend doc §5)."""

    edge_pct: float
    kelly_stake_fraction: float
    recommended: bool

    clv_pct: float
    clv_bps: float
    settlement: str
    """'win' | 'loss' | 'push', from `settlement.settle`."""

    fold: int
    """Walk-forward fold that scored this row. Fold k was calibrated only on
    data strictly earlier than fold k."""
