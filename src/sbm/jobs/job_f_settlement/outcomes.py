"""Grading a finished game's picks, and computing CLV at the only time it exists.

**Settlement replays the market plugin over the realized score.** Feed the final
runs in as a single "draw" and the market's own probability collapses to 1.0 or
0.0 — so there is no per-market settlement branch to keep in sync with
`markets/`, and adding a market adds no code here. That is
`core.backtest.settlement.settle`, which is pure and sport-agnostic; it is not
`core.backtest.evaluate_game`, which is backtest-only and raises without a
closing quote.

**A missing close is a null, never a raise.** `settle`'s own docstring says
'void' is a scheduling fact a result row cannot express, so those games are
graded here rather than passed down. And a game that was postponed, or one
whose closing sweep was skipped for budget (§2.5) or missed its window, simply
has no `closing_prob` — `pick_settlements.clv_pct` and `closing_prob` are both
nullable for exactly this. Fabricating a close to fill them would put an
invented number into the metric the whole system is graded on.

`clv_pct` is RELATIVE — `(closing_prob - bet_prob) / bet_prob`, straight from
`core.clv.compute_clv`. `v_pick_clv_live`'s live column is absolute and roughly
2x apart at typical prices; the two are never mixed (web/README "Two CLV units").
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from sbm.contracts.market import Market
from sbm.core.backtest.settlement import settle
from sbm.core.clv import compute_clv
from sbm.jobs.rpc import UnsettledPick
from sbm.store.client import PostgrestClient

VOID_STATUSES = frozenset({"postponed", "cancelled"})
"""Backend doc §3.2's fourth outcome — a scheduling fact, not a score."""

TABLE = "pick_settlements"


@dataclass(frozen=True, slots=True)
class SettlementRow:
    """One `pick_settlements` row (insert-once, post-game, §3.2)."""

    pick_id: int
    outcome: str
    bet_prob: float | None
    closing_prob: float | None
    clv_pct: float | None

    def to_json(self) -> dict[str, Any]:
        return {
            "pick_id": self.pick_id,
            "outcome": self.outcome,
            "bet_prob": self.bet_prob,
            "closing_prob": self.closing_prob,
            "clv_pct": self.clv_pct,
        }


def settle_picks(
    picks: list[UnsettledPick], markets: Mapping[str, Market]
) -> list[SettlementRow]:
    """Grade every pick whose game has reached a terminal state."""
    return [_settle_one(pick, markets) for pick in picks if _is_terminal(pick)]


def write_settlements(client: PostgrestClient, rows: list[SettlementRow]) -> int:
    """Plain INSERT — `pick_settlements` is append-only (§3.1).

    TODO(db): this belongs beside `write_results` in `sbm.store.facts` as a
    typed writer; `store/` has no `pick_settlements` shape today, and adding
    one is in `db`'s directory. Reported. Until then this uses
    `PostgrestClient.insert`, which is documented as "the only write mode for
    append-only tables" and is exactly that.
    """
    client.insert(TABLE, [row.to_json() for row in rows])
    return len(rows)


def _is_terminal(pick: UnsettledPick) -> bool:
    """Terminal means 'final with a score' or 'will never be played'.

    An in-progress game is skipped and picked up by the next night's run —
    `fn_unsettled_picks` is keyed on the absence of a settlement row, so
    nothing is lost by waiting.
    """
    if pick.game_status in VOID_STATUSES:
        return True
    return pick.game_status == "final" and pick.home_score is not None and pick.away_score is not None


def _settle_one(pick: UnsettledPick, markets: Mapping[str, Market]) -> SettlementRow:
    clv = _clv(pick)
    if pick.game_status in VOID_STATUSES:
        # No result to grade and no close to compare against — the row exists so
        # the pick is accounted for, not so it contributes a number.
        return SettlementRow(pick.pick_id, "void", pick.bet_prob, None, None)
    outcome = settle(
        markets[pick.market],
        pick.side,
        pick.line,
        np.array([[float(pick.home_score or 0), float(pick.away_score or 0)]], dtype=np.float64),
    )
    return SettlementRow(pick.pick_id, outcome, pick.bet_prob, pick.closing_prob, clv)


def _clv(pick: UnsettledPick) -> float | None:
    """Relative CLV, or None when either leg is missing or degenerate.

    `compute_clv` requires both probabilities strictly inside (0, 1) and raises
    otherwise; a 0 or 1 here would mean a de-vig produced a certainty, which is
    a data problem rather than a pick worth grading for CLV.
    """
    bet, close = pick.bet_prob, pick.closing_prob
    if bet is None or close is None:
        return None
    if not (0.0 < bet < 1.0 and 0.0 < close < 1.0):
        return None
    return compute_clv(bet, close).clv_pct
