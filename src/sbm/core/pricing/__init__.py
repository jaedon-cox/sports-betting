"""De-vig, edge and Kelly sizing — sport-agnostic, market-odds consumers only.

Market odds enter the system here and only here (plus `core/clv.py`); never
as a `FeatureBuilder`/`Distribution` input (model doc A1).
"""

from sbm.core.pricing.devig import (
    devig,
    devig_additive,
    devig_multiplicative,
    devig_power,
    devig_shin,
    devig_sides,
    recommended_method,
)
from sbm.core.pricing.edge import edge_pct
from sbm.core.pricing.kelly import (
    DEFAULT_KELLY_FRACTION,
    full_kelly_fraction,
    kelly_stake_fraction,
)
from sbm.core.pricing.odds_math import (
    american_to_decimal_odds,
    american_to_implied_prob,
    implied_prob_to_american,
)

__all__ = [
    "DEFAULT_KELLY_FRACTION",
    "american_to_decimal_odds",
    "american_to_implied_prob",
    "devig",
    "devig_additive",
    "devig_multiplicative",
    "devig_power",
    "devig_shin",
    "devig_sides",
    "edge_pct",
    "full_kelly_fraction",
    "implied_prob_to_american",
    "kelly_stake_fraction",
    "recommended_method",
]
