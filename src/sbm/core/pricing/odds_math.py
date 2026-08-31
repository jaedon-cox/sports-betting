"""American-odds <-> probability conversions.

Pure math shared by de-vig and Kelly sizing. No I/O, no sport knowledge.
"""

from __future__ import annotations


def american_to_implied_prob(price: int) -> float:
    """Raw (vig-included) implied probability from an American price."""
    if price == 0:
        raise ValueError("American odds price cannot be 0")
    if price > 0:
        return 100.0 / (price + 100.0)
    return -price / (-price + 100.0)


def implied_prob_to_american(prob: float) -> int:
    """Fair American price for a probability. Inverse of `american_to_implied_prob`."""
    if not 0.0 < prob < 1.0:
        raise ValueError(f"probability must be in (0, 1), got {prob}")
    if prob >= 0.5:
        return round(-prob / (1.0 - prob) * 100.0)
    return round((1.0 - prob) / prob * 100.0)


def american_to_decimal_odds(price: int) -> float:
    """Decimal (European) odds — total payout per unit staked, including stake."""
    if price == 0:
        raise ValueError("American odds price cannot be 0")
    if price > 0:
        return 1.0 + price / 100.0
    return 1.0 + 100.0 / (-price)
