"""Aggregating evaluated picks into the numbers a backtest is judged on.

The ordering here is the point. **CLV is the gate metric** and it is computed
over every evaluated pick, not just the recommended ones (model doc §7).
**Calibration** is the second gate — a model whose probabilities are right is
the only kind whose edge estimate means anything (A5). **ROI is reported and
never gated on**: it is noise below ~`ROI_MIN_BETS` bets (CLAUDE.md), which is
why `RoiSummary` carries `above_noise_floor` rather than leaving a reader to
guess whether a number is signal.

No pass/fail CLV threshold is asserted anywhere in this module. The docs fix
CLV as the gate but never name the bar it has to clear (model doc §7 leaves the
operational layer open), and inventing one here would quietly make it look
decided.

"pct" fields are ratios, not hundredths — matching `clv.CLVResult.clv_pct` and
`pricing.edge_pct`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from sbm.core.backtest.types import EvaluatedPick
from sbm.core.calibration import ReliabilityBucket, expected_calibration_error, reliability_buckets
from sbm.core.pricing import american_to_decimal_odds

ROI_MIN_BETS = 2000
"""Below this many settled bets, ROI is noise and says nothing about edge."""


@dataclass(frozen=True, slots=True)
class ClvSummary:
    """The gate metric. `avg_clv_bps` is the unit CLV is usually quoted in."""

    n: int
    avg_clv_pct: float
    avg_clv_bps: float
    positive_rate: float


@dataclass(frozen=True, slots=True)
class CalibrationSummary:
    """ECE plus the reliability buckets the frontend renders (backend doc §3.3).

    Pushes are excluded — they have no binary outcome to be calibrated against.
    """

    n: int
    ece: float
    brier: float
    buckets: tuple[ReliabilityBucket, ...]


@dataclass(frozen=True, slots=True)
class RoiSummary:
    """Units are fractions of bankroll (`kelly_stake_fraction`), never dollars
    (backend doc §3.5). Reported, never gated on."""

    n_bets: int
    units_staked: float
    units_won: float
    roi_pct: float
    wins: int
    losses: int
    pushes: int
    above_noise_floor: bool


@dataclass(frozen=True, slots=True)
class BacktestReport:
    picks: tuple[EvaluatedPick, ...]
    clv: ClvSummary
    """Over every evaluated pick — the headline gate number."""
    clv_recommended: ClvSummary
    """Over the subset actually recommended; a large gap from `clv` means the
    bet filter is selecting the wrong rows."""
    calibration: CalibrationSummary
    roi: RoiSummary
    n_games_scored: int
    n_games_excluded: int
    """Games consumed by the train/calibration slices and never scored — see
    `engine.run_backtest`."""


def summarize(
    picks: Sequence[EvaluatedPick], *, n_games_scored: int, n_games_excluded: int
) -> BacktestReport:
    """Full report over one walk-forward run's picks."""
    return BacktestReport(
        picks=tuple(picks),
        clv=clv_summary(picks),
        clv_recommended=clv_summary([p for p in picks if p.recommended]),
        calibration=calibration_summary(picks),
        roi=roi_summary([p for p in picks if p.recommended]),
        n_games_scored=n_games_scored,
        n_games_excluded=n_games_excluded,
    )


def clv_summary(picks: Sequence[EvaluatedPick]) -> ClvSummary:
    if not picks:
        nan = float("nan")
        return ClvSummary(n=0, avg_clv_pct=nan, avg_clv_bps=nan, positive_rate=nan)
    clv = np.array([p.clv_pct for p in picks], dtype=np.float64)
    return ClvSummary(
        n=len(picks),
        avg_clv_pct=float(clv.mean()),
        avg_clv_bps=float(clv.mean() * 10_000.0),
        positive_rate=float((clv > 0.0).mean()),
    )


def calibration_summary(
    picks: Sequence[EvaluatedPick], *, n_buckets: int = 10
) -> CalibrationSummary:
    scored = [p for p in picks if p.settlement != "push"]
    if not scored:
        return CalibrationSummary(n=0, ece=float("nan"), brier=float("nan"), buckets=())
    prob = np.array([p.model_prob for p in scored], dtype=np.float64)
    won = np.array([1.0 if p.settlement == "win" else 0.0 for p in scored], dtype=np.float64)
    return CalibrationSummary(
        n=len(scored),
        ece=expected_calibration_error(prob, won, n_buckets=n_buckets),
        brier=float(np.mean((prob - won) ** 2)),
        buckets=tuple(reliability_buckets(prob, won, n_buckets=n_buckets)),
    )


def roi_summary(picks: Sequence[EvaluatedPick]) -> RoiSummary:
    """Profit in bankroll units: a push returns the stake, a loss forfeits it.

    Push stakes are left out of `units_staked` — they resolve at exactly zero,
    so counting them would shrink the ratio without any result having gone
    against us. A convention choice, not a doc requirement; `pushes` is reported
    separately so a reader can recompute the other convention.
    """
    staked = 0.0
    won = 0.0
    tally = {"win": 0, "loss": 0, "push": 0}
    for pick in picks:
        tally[pick.settlement] += 1
        if pick.settlement == "push":
            continue
        staked += pick.kelly_stake_fraction
        if pick.settlement == "win":
            won += pick.kelly_stake_fraction * (american_to_decimal_odds(pick.price_american) - 1.0)
        else:
            won -= pick.kelly_stake_fraction
    n_bets = tally["win"] + tally["loss"]
    return RoiSummary(
        n_bets=n_bets,
        units_staked=staked,
        units_won=won,
        roi_pct=won / staked if staked > 0 else float("nan"),
        wins=tally["win"],
        losses=tally["loss"],
        pushes=tally["push"],
        above_noise_floor=n_bets >= ROI_MIN_BETS,
    )
