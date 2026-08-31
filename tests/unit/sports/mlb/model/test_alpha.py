"""alpha.py: direction sanity and range clipping for the matchup-varying dispersion model.

Coefficient signs are enforced here, not just documented — a sign flip on any of
these silently miscalibrates exactly the totals/run-line edges the doc cares about
(see mean.py's test file for the same discipline applied there).
"""

from __future__ import annotations

import pytest

from sbm.sports.mlb.model.alpha import DEFAULT_ALPHA_MODEL, AlphaModel

BASE_INPUTS: dict[str, float] = dict(csw_pct=0.0, gb_pct=0.0, contact_quality=0.0)

# expected sign of d(alpha)/d(field), holding every other input at the baseline above.
EXPECTED_SIGN: dict[str, int] = {
    "csw_pct": -1,  # higher opposing-starter CSW% -> more predictable -> lower alpha
    "gb_pct": -1,  # higher opposing-starter GB% -> more predictable -> lower alpha
    "contact_quality": +1,  # higher opposing-lineup contact quality -> higher alpha
}


@pytest.mark.parametrize("field", EXPECTED_SIGN)
def test_alpha_coefficient_direction(field: str) -> None:
    low = dict(BASE_INPUTS, **{field: -1.0})
    high = dict(BASE_INPUTS, **{field: 1.0})
    alpha_low = DEFAULT_ALPHA_MODEL.predict_one(**low)
    alpha_high = DEFAULT_ALPHA_MODEL.predict_one(**high)
    expected = EXPECTED_SIGN[field]
    assert (alpha_high - alpha_low) * expected > 0, (
        f"{field}: expected sign {expected:+d} on alpha, got "
        f"alpha_low={alpha_low:.4f} alpha_high={alpha_high:.4f}"
    )


def test_alpha_never_a_global_constant_across_inputs() -> None:
    """A6: alpha must vary by matchup — two different profiles must not collapse
    to the same number."""
    a = DEFAULT_ALPHA_MODEL.predict_one(csw_pct=0.30, gb_pct=0.35, contact_quality=0.5)
    b = DEFAULT_ALPHA_MODEL.predict_one(csw_pct=0.22, gb_pct=0.50, contact_quality=-0.5)
    assert a != b


def test_alpha_clipped_to_configured_range() -> None:
    model = AlphaModel(alpha_min=0.1, alpha_max=2.0)
    huge = model.predict_one(csw_pct=-10.0, gb_pct=-10.0, contact_quality=10.0)
    tiny = model.predict_one(csw_pct=10.0, gb_pct=10.0, contact_quality=-10.0)
    assert huge == 2.0
    assert tiny == 0.1
