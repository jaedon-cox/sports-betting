"""25% fractional Kelly staking — a FRACTION OF BANKROLL, never a dollar amount.

`picks.kelly_stake_fraction` is the only stake figure ever persisted (backend
doc §3.5); `$ stake` is a live `fraction × current bankroll` computation the
frontend does, never something we write to the DB.
"""

from __future__ import annotations

from sbm.core.pricing.odds_math import american_to_decimal_odds

DEFAULT_KELLY_FRACTION = 0.25
"""25% fractional Kelly — decided, model doc §7."""


def full_kelly_fraction(model_prob: float, price_american: int) -> float:
    """Un-fractioned Kelly stake as a fraction of bankroll.

    Uses the price actually on offer (not the de-vigged fair price) because
    sizing must reflect what you're paid; the edge itself comes from
    comparing `model_prob` against the de-vigged fair prob (`edge.py`).
    Can be negative (no edge) or > 1 (very large edge) — callers use
    `kelly_stake_fraction` for the clamped, fractional version actually bet.
    """
    if not 0.0 <= model_prob <= 1.0:
        raise ValueError(f"model_prob must be in [0, 1], got {model_prob}")
    b = american_to_decimal_odds(price_american) - 1.0  # net odds per unit staked
    return model_prob - (1.0 - model_prob) / b


def kelly_stake_fraction(
    model_prob: float,
    price_american: int,
    *,
    fraction: float = DEFAULT_KELLY_FRACTION,
) -> float:
    """25%-fractional Kelly stake, clamped to [0, 1] of bankroll.

    Never negative (a negative full-Kelly means no edge -> stake 0, not a
    short position) and never more than the whole bankroll (guards against a
    pathological edge blowing past 100%).
    """
    if not 0.0 < fraction <= 1.0:
        raise ValueError(f"fraction must be in (0, 1], got {fraction}")
    stake = fraction * full_kelly_fraction(model_prob, price_american)
    return max(0.0, min(stake, 1.0))
