"""De-vig: strip bookmaker overround from raw American-odds prices.

FINAL DECISION (`main`, superseding model doc §7's per-market split):
`power` is seeded as `devig_method` for all three markets — moneyline,
total, spread — not split by how near-even the price is. §7 originally
picked power/multiplicative for moneylines and named additive as acceptable
for near-even totals, on the premise that additive understates the
favorite's fair prob at extreme prices. That premise doesn't hold for 2-way
books (proof + simulation below), and this system prices nothing but 2-way
books, so the split rested on a false distinction; a single method also
keeps `record_summary`/`mv_clv_trend`'s blended-across-markets CLV number
from mixing method artifacts between its components. The per-market
`devig_method` column in `db`'s `markets` table exists precisely so this can
be revisited against real (not simulated) data later.

"Locked" is a correctness requirement, not a style preference. CLV compares a
pick's `bet_prob` against its `closing_prob`, so if the method can change
between the open snapshot and the close, the difference between the two
numbers is part method artifact and part signal. An ordinary moneyline drift
from -150/+130 to -190/+160 moves the favorite's fair prob by 78 bps purely by
switching multiplicative -> power; CLV edges live at tens of bps, so the
artifact can exceed what we are trying to measure.

Therefore `method` is a REQUIRED argument on every entry point here. The
method actually in force lives in the `markets` lookup table as
`devig_method`, is persisted onto `line_snapshots` and `picks` alongside the
probability it produced, and is threaded through explicitly by the caller.
There is no call-time fallback, by design — see `recommended_method` for the
configuration-time helper (currently unused for production seeding, since
the decision above hardcodes `power`; kept for the future per-market
re-evaluation).

Methods:

- `devig_power`          — the production default for all three markets.
  Solves an exponent so probabilities renormalize through `p ** k` instead
  of linear scaling; corrects the favorite-longshot bias the two methods
  below leave behind.
- `devig_multiplicative` — proportional normalization. Cheap, standard,
  slightly understates the favorite's fair prob at extreme prices. Not
  currently used in production; kept selectable per the decision above.
- `devig_additive`       — subtracts the overround evenly across outcomes.
  §7 named this for near-even totals; NOT used in production (see decision
  above). For the 2-way books this system prices, it is provably always
  non-negative (`fair_fav = (raw_fav - raw_dog + 1)/2`, bounded in (0,1) by
  construction) and — verified over 50k simulated books, `main`'s
  reproduction found ZERO counterexamples — tracks `devig_power` *more*
  closely than `devig_multiplicative` does as prices skew. That is the
  reverse of §7's stated rationale for excluding it from skewed moneylines,
  which is why the split was dropped rather than kept as originally written.
- `devig_shin`           — Shin's (1992) insider-trading model; the most
  theoretically complete, solves for an informed-money fraction `z`. Opt-in
  only, not a production default.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from scipy.optimize import brentq

from sbm.core.pricing.odds_math import american_to_implied_prob

SKEW_THRESHOLD = 0.20
"""Raw-implied-prob spread (max - min) above which a market is 'skewed'
enough that proportional de-vig measurably understates the favorite's fair
prob (model doc §7)."""


def _raw_probs(prices_american: Sequence[int]) -> list[float]:
    if len(prices_american) < 2:
        raise ValueError("de-vig needs at least two competing prices")
    return [american_to_implied_prob(p) for p in prices_american]


def devig_multiplicative(prices_american: Sequence[int]) -> list[float]:
    """Proportional de-vig: normalize raw implied probs to sum to 1."""
    raw = _raw_probs(prices_american)
    total = sum(raw)
    return [p / total for p in raw]


def devig_power(prices_american: Sequence[int]) -> list[float]:
    """Power (logarithmic) de-vig: solve `p_i = raw_i ** k` for k s.t. sum == 1.

    Unlike proportional scaling, this doesn't divide every side by the same
    constant — the exponent shrinks each side by an amount that depends on
    its own raw probability, which is what corrects the favorite more than
    the underdog at extreme prices.
    """
    raw = _raw_probs(prices_american)

    def residual(k: float) -> float:
        return sum(p**k for p in raw) - 1.0

    k = brentq(residual, 0.1, 10.0, xtol=1e-12)
    return [p**k for p in raw]


def devig_shin(prices_american: Sequence[int]) -> list[float]:
    """Shin's method: solve for the insider/informed-money fraction `z`.

    p_i = (sqrt(z^2 + 4*(1-z)*raw_i^2/B) - z) / (2*(1-z)), B = sum(raw),
    with z chosen so the resulting probabilities sum to 1. z -> 0 recovers
    (approximately) the no-overround case.
    """
    raw = _raw_probs(prices_american)
    total = sum(raw)

    def shin_probs(z: float) -> list[float]:
        return [
            (math.sqrt(z**2 + 4.0 * (1.0 - z) * (p**2) / total) - z) / (2.0 * (1.0 - z))
            for p in raw
        ]

    def residual(z: float) -> float:
        return sum(shin_probs(z)) - 1.0

    z = brentq(residual, 0.0, 0.999, xtol=1e-12)
    return shin_probs(z)


def devig_additive(prices_american: Sequence[int]) -> list[float]:
    """Additive de-vig: subtract an equal share of the overround from each raw
    prob (`p_i = raw_i - (sum(raw) - 1) / n`). §7 names this for near-even
    totals; it is NOT the production method — `devig_power` is seeded for
    all three markets (see module docstring for the full decision and why
    the per-market split it originally implied didn't survive scrutiny).

    For n=2 (every market this system prices today) this is provably always
    non-negative: `fair_favorite = (raw_favorite - raw_underdog + 1) / 2`,
    which is > 0 whenever `raw_underdog >= 0` and `raw_favorite < 1`, with no
    dependence on how skewed the price is. The raise-guard below is a
    defensive check for n>2 markets (e.g. a hypothetical 3-way sport), where
    a sufficiently extreme longshot outcome can in principle drive its share
    negative — not something reachable by anything this system prices today.
    """
    raw = _raw_probs(prices_american)
    overround = sum(raw) - 1.0
    share = overround / len(raw)
    fair = [p - share for p in raw]
    if any(p <= 0.0 for p in fair):
        raise ValueError(
            "additive de-vig produced a non-positive probability — prices are too "
            "skewed for this method; use devig_power instead"
        )
    return fair


def recommended_method(prices_american: Sequence[int]) -> str:
    """multiplicative vs. power, chosen by raw-probability skew (model doc §7).

    CONFIGURATION-TIME ONLY. Call this once, offline, to choose the
    `devig_method` stored per (sport, market) — e.g. in `db`'s `markets`
    lookup table — never per snapshot or per request. See the module
    docstring for why a per-call selector corrupts CLV.
    """
    raw = _raw_probs(prices_american)
    spread = max(raw) - min(raw)
    return "power" if spread >= SKEW_THRESHOLD else "multiplicative"


_METHODS = {
    "multiplicative": devig_multiplicative,
    "power": devig_power,
    "additive": devig_additive,
    "shin": devig_shin,
}


def devig(prices_american: Sequence[int], *, method: str) -> list[float]:
    """De-vig raw American prices into fair probabilities summing to 1.

    `method` is REQUIRED — one of {"multiplicative", "power", "additive",
    "shin"}. No default: the caller must pass the method locked for this
    (sport, market) so the same pick de-vigs identically at open and close.
    Use `recommended_method()` offline to choose that per-market default.
    """
    if method not in _METHODS:
        raise ValueError(f"unknown de-vig method {method!r}, expected one of {sorted(_METHODS)}")
    return _METHODS[method](prices_american)


def devig_sides(prices_by_side: Mapping[str, int], *, method: str) -> dict[str, float]:
    """Same as `devig`, keyed by side name — the shape most callers want
    (e.g. writing `line_snapshots.implied_prob_devigged` per side without
    tracking list-order-to-side mapping by hand). `method` is required; see
    `devig`.
    """
    sides = list(prices_by_side)
    fair = devig([prices_by_side[s] for s in sides], method=method)
    return dict(zip(sides, fair, strict=True))
