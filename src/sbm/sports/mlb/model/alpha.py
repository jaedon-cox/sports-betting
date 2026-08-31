"""Matchup-varying NB dispersion (model doc A6, §10.6).

A fixed alpha miscalibrates exactly the high- and low-variance games where totals
and run-line edges live. log(alpha) is modeled as a linear function of the opposing
starter's CSW%/GB% and the batting side's contact quality, so dispersion moves with
the actual talent on the field instead of assuming a league-average shape every night.

Uses CSW%, not K%: the doc's actual v1 feature stack cuts standalone K%/BB% as a
model input (§10.5) and keeps CSW% as the "fast-stabilizing skill signal" (§3.1) —
same directional role §10.6 describes for "starter K%" (a pitcher who generates more
called-strikes-plus-whiffs allows a more predictable run environment), different
(real, ingest-provided) column.

Coefficients below are directional priors, not fit — `alpha` must be earned
empirically against realized run variance before these numbers are trusted (doc §6).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class AlphaModel:
    """log(alpha) = intercept + b_csw*CSW% + b_gb*GB% + b_contact*contact_quality.

    A pitcher who misses more bats (higher CSW%) or induces more grounders (higher
    GB%) produces a more predictable run environment (fewer high-variance
    extra-base/air events) -> lower alpha. A higher-contact-quality opposing lineup
    puts more balls in play with authority -> higher alpha. Replace via a fitted
    model once graded against realized run variance.
    """

    intercept: float = 0.0
    coef_csw_pct: float = -1.5
    coef_gb_pct: float = -0.5
    coef_contact_quality: float = 1.0
    alpha_min: float = 0.05
    alpha_max: float = 4.0

    def predict(
        self,
        csw_pct: pd.Series | np.ndarray | float,
        gb_pct: pd.Series | np.ndarray | float,
        contact_quality: pd.Series | np.ndarray | float,
    ) -> np.ndarray:
        """Vectorized alpha for one or many starter/matchup rows, clipped to a
        sane range so a feature outlier can't collapse the NB into a
        near-degenerate or explosively-wide distribution."""
        log_alpha = (
            self.intercept
            + self.coef_csw_pct * np.asarray(csw_pct, dtype=np.float64)
            + self.coef_gb_pct * np.asarray(gb_pct, dtype=np.float64)
            + self.coef_contact_quality * np.asarray(contact_quality, dtype=np.float64)
        )
        return np.clip(np.exp(log_alpha), self.alpha_min, self.alpha_max)

    def predict_one(self, csw_pct: float, gb_pct: float, contact_quality: float) -> float:
        """Scalar convenience wrapper around `predict` for single-game callers
        (e.g. `vertical.py`'s per-side wiring)."""
        return float(self.predict(csw_pct, gb_pct, contact_quality))


DEFAULT_ALPHA_MODEL = AlphaModel()
