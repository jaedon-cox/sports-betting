"""recency/: EWMA weighting and half-life decay.

The decisive test here is `test_numerator_and_denominator_are_weighted_separately`
— weighting the per-game *rate* instead would be a different (and wrong)
estimator whenever opportunity counts vary between games (model doc §10.1).
"""

from __future__ import annotations

import numpy as np
import pytest

from sbm.core.recency import HALF_LIVES_GAMES, decay_factor, ewma_asof, ewma_rate


def test_decay_factor_halves_over_the_half_life() -> None:
    lam = decay_factor(5.0)
    assert lam**5.0 == pytest.approx(0.5)


def test_decay_factor_is_increasing_in_half_life() -> None:
    """A longer half-life forgets more slowly."""
    assert decay_factor(5.0) < decay_factor(20.0) < 1.0


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_nonpositive_half_life_rejected(bad: float) -> None:
    with pytest.raises(ValueError):
        decay_factor(bad)


def test_half_life_table_matches_the_doc() -> None:
    """§10.1's four signal families, each a (min, max) range the sport vertical
    picks a point inside — not a single value core decides."""
    assert set(HALF_LIVES_GAMES) == {
        "bullpen_fatigue",
        "bullpen_skill",
        "team_offense",
        "starters",
    }
    assert all(lo < hi for lo, hi in HALF_LIVES_GAMES.values())


def test_numerator_and_denominator_are_weighted_separately() -> None:
    """One event in one opportunity, then none in a hundred.

    Weighting the *rates* [1.0, 0.0] would give lam/(1+lam) — the big second
    game barely counts. Weighting numerator and denominator separately gives
    lam/(100+lam), because 100 opportunities are 100 opportunities. The gap
    between those two numbers is the whole decision in §10.1.
    """
    events = np.array([1.0, 0.0])
    opportunities = np.array([1.0, 100.0])
    lam = decay_factor(10.0)
    rate, _ = ewma_asof(events, opportunities, 10.0)
    assert rate == pytest.approx(lam / (100.0 + lam))
    assert rate != pytest.approx(lam / (1.0 + lam))


def test_row_t_excludes_its_own_observation() -> None:
    """Point-in-time: the value emitted for game t is knowable before game t is
    played, which is what lets the same function serve live and backtest."""
    events = np.array([1.0, 1.0, 0.0])
    opportunities = np.array([1.0, 1.0, 1.0])
    rate, _ = ewma_rate(events, opportunities, 10.0)
    assert np.isnan(rate[0])
    assert rate[1] == pytest.approx(1.0)
    assert rate[2] == pytest.approx(1.0)


def test_rate_is_nan_until_the_entity_has_history() -> None:
    rate, ess = ewma_rate(np.array([2.0]), np.array([5.0]), 5.0)
    assert np.isnan(rate[0])
    assert ess[0] == 0.0


def test_asof_folds_in_every_row_given() -> None:
    """`ewma_asof` is the live-scoring value: everything so far, nothing after."""
    events = np.array([1.0, 3.0, 2.0])
    opportunities = np.array([4.0, 5.0, 6.0])
    rate_series, ess_series = ewma_rate(np.append(events, 0.0), np.append(opportunities, 0.0), 8.0)
    assert ewma_asof(events, opportunities, 8.0) == (
        pytest.approx(rate_series[-1]),
        pytest.approx(ess_series[-1]),
    )


def test_asof_on_an_empty_log_is_nan_with_no_sample() -> None:
    assert np.isnan(ewma_asof(np.array([]), np.array([]), 5.0)[0])
    assert ewma_asof(np.array([]), np.array([]), 5.0)[1] == 0.0


def test_constant_rate_is_reproduced_exactly() -> None:
    """Any weighting of identical rates is that rate — a sanity floor."""
    events = np.array([2.0, 4.0, 1.0, 3.0])
    opportunities = events * 5.0
    rate, _ = ewma_asof(events, opportunities, 12.0)
    assert rate == pytest.approx(0.2)


def test_recent_games_dominate_distant_ones() -> None:
    """Same totals, opposite order: the estimate follows the recent games."""
    early_hot = ewma_asof(np.array([5.0, 0.0]), np.array([5.0, 5.0]), 2.0)[0]
    late_hot = ewma_asof(np.array([0.0, 5.0]), np.array([5.0, 5.0]), 2.0)[0]
    assert late_hot > early_hot


def test_effective_sample_size_grows_toward_the_half_life_ceiling() -> None:
    """Kish ESS in units of games — a long log saturates rather than growing
    without bound, which is what makes it usable as a shrinkage weight."""
    lam = decay_factor(10.0)
    _, ess = ewma_rate(np.ones(400), np.ones(400), 10.0)
    assert ess[1] == pytest.approx(1.0)
    assert np.all(np.diff(ess) >= -1e-12)
    assert ess[-1] == pytest.approx((1.0 + lam) / (1.0 - lam), rel=1e-3)


def test_length_mismatch_rejected() -> None:
    with pytest.raises(ValueError):
        ewma_rate(np.array([1.0, 2.0]), np.array([1.0]), 5.0)
