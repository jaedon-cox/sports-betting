"""Closing Line Value: bet price vs. the T-5min Pinnacle close (model doc §7).

Computed for every evaluated pick, not just recommended ones, so the track
record includes games the model declined to bet — persisted as
`pick_settlements.clv_pct` alongside `bet_prob`/`closing_prob` (backend doc
§3.2).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CLVResult:
    clv_pct: float
    """`(closing_prob - bet_prob) / bet_prob`. Positive means the market's
    fair prob for this side rose *after* the bet was placed — i.e. the price
    taken was better than the closing price, independent of the outcome."""
    clv_bps: float
    """`clv_pct` in basis points (x 10,000) — the unit CLV is usually quoted in."""


def compute_clv(bet_prob: float, closing_prob: float) -> CLVResult:
    """CLV from de-vigged fair probabilities at bet time and at the close.

    Both inputs must already be de-vigged (`pricing/devig.py`) fair probs for
    the SAME side and the SAME book (Pinnacle) — mixing books breaks
    apples-to-apples comparison (backend doc §5, "book consistency"), and
    `closing_prob` must come from the T-5min-to-first-pitch Pinnacle snapshot
    specifically (model doc §7).
    """
    for name, p in (("bet_prob", bet_prob), ("closing_prob", closing_prob)):
        if not 0.0 < p < 1.0:
            raise ValueError(f"{name} must be in (0, 1), got {p}")
    pct = (closing_prob - bet_prob) / bet_prob
    return CLVResult(clv_pct=pct, clv_bps=pct * 10_000.0)
