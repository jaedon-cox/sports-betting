"""Point-in-time EWMA with the numerator and denominator weighted separately.

Never weight the per-game *rate* directly: an entity's EWMA rate is
`EW(sum of events) / EW(sum of opportunities)`, which is the statistically
correct way to combine rate data with varying opportunity size per row (see
project memory: recency-weighting-decision, §4.6). Every value emitted for
row t is computed from rows strictly *before* t (row t's own counts are
folded in only for row t+1 onward) — this is what lets the same function
serve both live scoring and backtest reconstruction without leakage.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from sbm.core.recency.halflife import decay_factor


def ewma_rate(
    events: NDArray[np.float64],
    opportunities: NDArray[np.float64],
    half_life_games: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Point-in-time EWMA rate and effective sample size for one entity's log.

    `events`/`opportunities` are chronologically ordered per-row counts for a
    *single* entity (e.g. one pitcher's game log) — rows must be games the
    entity actually appeared in, not a full season calendar with zero-filled
    off days, or the effective sample size below over-counts.

    Returns `(rate, effective_sample_size)`, each shape (n,); index t reflects
    only rows `[0, t)`. `rate[t]` is `nan` until the entity has any prior
    opportunities.

    `effective_sample_size` is the Kish design-effect ESS
    `(sum w)^2 / sum(w^2)` of the decay weights folded in so far, in units of
    *games* (matching how half-lives are specified, model doc §10.1) — use it
    to shrink `rate` toward a prior when an entity's history is thin (e.g.
    early season, a newly-promoted arm).
    """
    n = len(events)
    if len(opportunities) != n:
        raise ValueError("events and opportunities must be the same length")
    lam = decay_factor(half_life_games)

    rate = np.empty(n, dtype=np.float64)
    ess = np.empty(n, dtype=np.float64)

    ew_num = 0.0
    ew_denom = 0.0
    w_sum = 0.0
    w_sq_sum = 0.0

    for t in range(n):
        rate[t] = ew_num / ew_denom if ew_denom > 0 else np.nan
        ess[t] = (w_sum**2 / w_sq_sum) if w_sq_sum > 0 else 0.0

        ew_num = ew_num * lam + events[t]
        ew_denom = ew_denom * lam + opportunities[t]
        w_sum = w_sum * lam + 1.0
        w_sq_sum = w_sq_sum * lam**2 + 1.0

    return rate, ess


def ewma_asof(
    events: NDArray[np.float64],
    opportunities: NDArray[np.float64],
    half_life_games: float,
) -> tuple[float, float]:
    """Single current `(rate, effective_sample_size)` after folding in every
    given row — the point-in-time value for a game that hasn't happened yet,
    whose own row is therefore *not* in `events`/`opportunities`.

    This is what a live `FeatureBuilder` wants: one scalar per entity as of
    `as_of`, computed from that entity's rows with `game_date < as_of`
    (filtering/ordering is the feature layer's job, not core's — this
    function only does the numeric fold). Implemented as `ewma_rate` over the
    given history plus one dummy trailing row, reading the value computed
    *for* that trailing row — which, by `ewma_rate`'s own row-exclusion rule,
    reflects everything strictly before it, i.e. every real row passed in.
    """
    if len(events) == 0:
        return float("nan"), 0.0
    events_ext = np.append(np.asarray(events, dtype=np.float64), 0.0)
    opportunities_ext = np.append(np.asarray(opportunities, dtype=np.float64), 0.0)
    rate, ess = ewma_rate(events_ext, opportunities_ext, half_life_games)
    return float(rate[-1]), float(ess[-1])
