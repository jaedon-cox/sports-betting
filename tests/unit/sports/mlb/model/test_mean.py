"""mean.py: direction sanity for the log-linear run-mean model.

Coefficients are directional priors, not yet fit (see mean.py's docstrings) — the
only thing standing between us and a silent sign flip until real fitting exists is
this test, per team-lead direction after the opp_starter_quality sign bug: enforce
by test, not by docstring.
"""

from __future__ import annotations

import pytest

from sbm.sports.mlb.model.mean import DEFAULT_MEAN_MODEL

BASE_INPUTS: dict[str, float | bool] = dict(
    off_wrc_plus_z=0.0,
    off_xwoba_z=0.0,
    opp_starter_siera_z=0.0,
    opp_bullpen_xfip_z=0.0,
    opp_bullpen_fatigue_raw=0.0,
    park_factor_log=0.0,
    weather_run_factor_log=0.0,
    is_home=False,
)

# expected sign of d(mu)/d(field), holding every other input at the baseline above.
EXPECTED_SIGN: dict[str, int] = {
    "off_wrc_plus_z": +1,  # better own offense (wRC+) -> more runs
    "off_xwoba_z": +1,  # better own offense (xwOBA vs opp hand) -> more runs
    "opp_starter_siera_z": +1,  # higher opposing SIERA (worse pitcher) -> more runs
    "opp_bullpen_xfip_z": +1,  # higher opposing bullpen xFIP (worse) -> more runs
    "opp_bullpen_fatigue_raw": +1,  # more fatigued opposing bullpen -> more runs allowed
    "park_factor_log": +1,  # more hitter-friendly park -> more runs
    "weather_run_factor_log": +1,  # more run-friendly weather -> more runs
}


@pytest.mark.parametrize("field", EXPECTED_SIGN)
def test_mean_coefficient_direction(field: str) -> None:
    low = dict(BASE_INPUTS, **{field: -1.0})
    high = dict(BASE_INPUTS, **{field: 1.0})
    mu_low = DEFAULT_MEAN_MODEL.predict_one(**low)  # type: ignore[arg-type]
    mu_high = DEFAULT_MEAN_MODEL.predict_one(**high)  # type: ignore[arg-type]
    expected = EXPECTED_SIGN[field]
    assert (mu_high - mu_low) * expected > 0, (
        f"{field}: expected sign {expected:+d} on mu, got mu_low={mu_low:.4f} mu_high={mu_high:.4f}"
    )


def test_home_field_bump_direction() -> None:
    away = DEFAULT_MEAN_MODEL.predict_one(**{**BASE_INPUTS, "is_home": False})  # type: ignore[arg-type]
    home = DEFAULT_MEAN_MODEL.predict_one(**{**BASE_INPUTS, "is_home": True})  # type: ignore[arg-type]
    assert home > away


def test_mu_is_always_positive() -> None:
    extreme = dict(BASE_INPUTS, off_wrc_plus_z=-5.0, opp_starter_siera_z=5.0)
    assert DEFAULT_MEAN_MODEL.predict_one(**extreme) > 0.0  # type: ignore[arg-type]
