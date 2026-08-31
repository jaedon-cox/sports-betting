"""Edge % = model probability vs. de-vigged market fair probability.

Model odds are never a model input (doc A1); this is the one place the two
probabilities meet, and only to compute an edge — never fed back as a
feature.
"""

from __future__ import annotations


def edge_pct(model_prob: float, market_fair_prob: float) -> float:
    """Signed edge: `model_prob - market_fair_prob`, both in [0, 1].

    Positive means the model thinks the side is more likely to win than the
    de-vigged market price implies — necessary, not sufficient (see
    `kelly.py`), for a +EV bet. Persisted as `picks.edge_pct` for every
    evaluated pick, not just recommended ones (model doc §7).
    """
    _validate_prob(model_prob, "model_prob")
    _validate_prob(market_fair_prob, "market_fair_prob")
    return model_prob - market_fair_prob


def _validate_prob(p: float, name: str) -> None:
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {p}")
