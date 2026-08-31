"""backtest/engine.py: the walk-forward loop.

Everything asserted here is a leakage or reproducibility property. A backtest
that quietly calibrates on its own test rows produces a beautiful CLV number
that predicts nothing, and the failure is invisible in the output — so it has
to be caught structurally.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest
from conftest import START, FakeVertical, make_game, season
from numpy.random import default_rng

from sbm.core.backtest import raw_probabilities, run_backtest
from sbm.core.backtest.engine import _folds
from sbm.core.calibration import chronological_split

METHOD = "power"


def _run(vertical, markets, games, **kwargs):
    return run_backtest(
        vertical,
        games,
        markets=markets,
        devig_method=METHOD,
        rng=default_rng(0),
        n_draws=kwargs.pop("n_draws", 2000),
        **kwargs,
    )


def test_only_the_test_slice_is_scored(vertical, markets: dict) -> None:
    """Train and calibration rows are consumed, never reported — scoring them
    would publish in-sample probabilities as out-of-sample ones."""
    games = season(100)
    report = _run(vertical, markets, games, train_frac=0.6, calibration_frac=0.2)
    assert report.n_games_scored == 20
    assert report.n_games_excluded == 80
    assert len(report.picks) == 20


def test_scored_games_are_the_chronologically_last_ones(vertical, markets: dict) -> None:
    games = season(100)
    report = _run(vertical, markets, games)
    assert {p.game_id for p in report.picks} == {g.game_id for g in games[-20:]}


def test_no_fold_is_calibrated_on_its_own_or_later_rows(
    vertical, markets: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The load-bearing property, asserted on the actual fit sets.

    Every game handed to `fit_calibrators` for fold k must be strictly earlier
    than every game fold k prices. This is the failure mode that produces a
    beautiful CLV number predicting nothing, and it is invisible in the output.
    """
    import sbm.core.backtest.engine as engine_module

    fit_sets: list[list[str]] = []
    real = engine_module.fit_calibrators

    def spy(history, *args, **kwargs):
        fit_sets.append([game.game_id for game in history])
        return real(history, *args, **kwargs)

    monkeypatch.setattr(engine_module, "fit_calibrators", spy)
    report = _run(vertical, markets, season(400), n_folds=4, n_draws=500)

    assert len(fit_sets) == 4
    for fold, history in enumerate(fit_sets):
        scored = {p.game_id for p in report.picks if p.fold == fold}
        assert scored, f"fold {fold} scored nothing"
        assert not set(history) & scored, "a fold was calibrated on its own rows"
        assert max(history) < min(scored), "a fold was calibrated on later rows"


def test_the_fit_set_grows_as_the_walk_moves_forward(
    vertical, markets: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each fold recalibrates on everything settled so far — what production
    does — rather than on a fixed window frozen at the start."""
    import sbm.core.backtest.engine as engine_module

    sizes: list[int] = []
    real = engine_module.fit_calibrators
    monkeypatch.setattr(
        engine_module,
        "fit_calibrators",
        lambda history, *a, **k: (sizes.append(len(history)), real(history, *a, **k))[1],
    )
    _run(vertical, markets, season(400), n_folds=4, n_draws=500)
    assert sizes == sorted(sizes)
    assert sizes[0] < sizes[-1]


def test_folds_are_contiguous_and_chronological(vertical, markets: dict) -> None:
    report = _run(vertical, markets, season(400), n_folds=4, n_draws=500)
    folds = sorted({p.fold for p in report.picks})
    assert folds == [0, 1, 2, 3]
    for earlier, later in zip(folds, folds[1:]):
        latest = max(p.game_id for p in report.picks if p.fold == earlier)
        earliest = min(p.game_id for p in report.picks if p.fold == later)
        assert latest < earliest


def test_calibration_actually_fires_once_history_is_deep_enough(vertical, markets: dict) -> None:
    """With a thin seed nothing is fit and `model_prob == raw_model_prob`; with
    a deep one the calibrator moves the number."""
    thin = _run(vertical, markets, season(40), n_draws=1000)
    deep = _run(vertical, markets, season(400), n_draws=1000)
    assert all(p.model_prob == p.raw_model_prob for p in thin.picks)
    assert any(p.model_prob != p.raw_model_prob for p in deep.picks)


def test_raw_probabilities_do_not_depend_on_the_fold_layout(markets: dict) -> None:
    """Scoring happens in one chronological pass before the folds are cut, so
    changing `n_folds` changes which calibrator a pick gets and nothing else —
    including which side it picks, which is why this compares against a
    standalone scoring pass rather than against the other run's picks."""
    games = season(200)
    scored = raw_probabilities(
        FakeVertical(),
        markets,
        sorted(games, key=lambda g: (g.as_of.ts, g.game_id)),
        n_draws=1000,
        rng=default_rng(0),
    )
    for n_folds in (2, 5):
        report = _run(FakeVertical(), markets, games, n_folds=n_folds, n_draws=1000)
        for pick in report.picks:
            assert pick.raw_model_prob == scored[(pick.game_id, pick.market, pick.side)]


def test_a_run_reproduces_exactly_for_a_fixed_seed(vertical, markets: dict) -> None:
    games = season(120)
    first = _run(vertical, markets, games, n_draws=1000)
    second = _run(FakeVertical(), markets, games, n_draws=1000)
    assert first.picks == second.picks


def test_a_different_seed_moves_the_monte_carlo(vertical, markets: dict) -> None:
    games = season(120)
    first = _run(vertical, markets, games, n_draws=1000)
    second = run_backtest(
        FakeVertical(),
        games,
        markets=markets,
        devig_method=METHOD,
        rng=default_rng(99),
        n_draws=1000,
    )
    assert first.picks != second.picks


def test_games_are_sorted_before_scoring(vertical, markets: dict) -> None:
    """Callers hand over rows in whatever order the DB returned them; the walk
    forward must be chronological regardless."""
    games = season(100)
    shuffled = list(default_rng(1).permutation(np.array(games, dtype=object)))
    assert _run(vertical, markets, shuffled).picks == _run(FakeVertical(), markets, games).picks


def test_a_well_specified_model_is_close_to_calibrated(vertical, markets: dict) -> None:
    """Outcomes are drawn from the very distribution the fake vertical models,
    so the backtest's ECE should be small — a sanity floor on the whole
    pipeline, not a claim about any real model."""
    report = _run(vertical, markets, season(400), n_draws=4000)
    assert report.calibration.n > 0
    assert report.calibration.ece < 0.15


def test_report_wires_clv_calibration_and_roi_together(vertical, markets: dict) -> None:
    report = _run(vertical, markets, season(200), n_draws=1000)
    assert report.clv.n == len(report.picks)
    assert report.roi.n_bets <= report.clv.n
    assert report.roi.above_noise_floor is False
    assert np.isfinite(report.clv.avg_clv_bps)


def test_short_test_slice_degrades_to_fewer_folds() -> None:
    """A test slice shorter than `n_folds` is still a backtest."""
    assert _folds(2, 4) == [[0], [1]]
    assert _folds(5, 2) == [[0, 1, 2], [3, 4]]


def test_folds_partition_the_test_slice_in_order() -> None:
    blocks = _folds(23, 4)
    assert [i for block in blocks for i in block] == list(range(23))


def test_empty_input_rejected(vertical, markets: dict) -> None:
    with pytest.raises(ValueError, match="at least one game"):
        _run(vertical, markets, [])


def test_zero_folds_rejected(vertical, markets: dict) -> None:
    with pytest.raises(ValueError, match="n_folds"):
        _run(vertical, markets, season(50), n_folds=0)


def test_split_fractions_are_forwarded(vertical, markets: dict) -> None:
    report = _run(vertical, markets, season(100), train_frac=0.4, calibration_frac=0.3)
    assert report.n_games_scored == 30


def test_the_engine_uses_each_games_own_as_of(vertical, markets: dict) -> None:
    """Point-in-time, per game — never one batch timestamp for the season."""
    games = [
        make_game(
            f"g{i:03d}",
            ts=START + timedelta(days=i),
            outcome=(5.0, 3.0) if i % 2 else (1.0, 4.0),
        )
        for i in range(50)
    ]
    _run(vertical, markets, games, n_draws=200)
    assert len(vertical.builder.calls) == 50
    assert [ts for _, ts in vertical.builder.calls] == [g.as_of.ts for g in games]


def test_split_boundaries_match_chronological_split(vertical, markets: dict) -> None:
    """The engine defers the A5 partition to `calibration/splits.py` rather than
    cutting its own — one splitter, one definition of "later"."""
    games = season(100)
    split = chronological_split([g.as_of.ts for g in games], train_frac=0.6, calibration_frac=0.2)
    expected = {g.game_id for g, keep in zip(games, split.test, strict=True) if keep}
    assert {p.game_id for p in _run(vertical, markets, games).picks} == expected
