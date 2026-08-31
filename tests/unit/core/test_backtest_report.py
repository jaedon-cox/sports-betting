"""backtest/report.py: the numbers a backtest is judged on, in the right order.

CLV first and over every evaluated pick; calibration second; ROI reported with
its noise floor attached and gated on by nothing.
"""

from __future__ import annotations

import math

import pytest

from sbm.core.backtest import (
    ROI_MIN_BETS,
    EvaluatedPick,
    calibration_summary,
    clv_summary,
    roi_summary,
    summarize,
)


def pick(
    *,
    clv_pct: float = 0.0,
    model_prob: float = 0.6,
    settlement: str = "win",
    recommended: bool = True,
    price: int = 100,
    stake: float = 0.01,
    market: str = "moneyline",
) -> EvaluatedPick:
    return EvaluatedPick(
        game_id="g001",
        market=market,
        side="home",
        line=None,
        price_american=price,
        raw_model_prob=model_prob,
        model_prob=model_prob,
        market_fair_prob=0.5,
        closing_prob=0.5,
        closing_line=None,
        edge_pct=model_prob - 0.5,
        kelly_stake_fraction=stake,
        recommended=recommended,
        clv_pct=clv_pct,
        clv_bps=clv_pct * 10_000.0,
        settlement=settlement,
        fold=0,
    )


def test_clv_summary_averages_and_counts_the_positive_share() -> None:
    picks = [pick(clv_pct=0.02), pick(clv_pct=-0.01), pick(clv_pct=0.05), pick(clv_pct=0.0)]
    summary = clv_summary(picks)
    assert summary.n == 4
    assert summary.avg_clv_pct == pytest.approx(0.015)
    assert summary.avg_clv_bps == pytest.approx(150.0)
    assert summary.positive_rate == pytest.approx(0.5)


def test_clv_is_reported_over_every_evaluated_pick() -> None:
    """Not just the bet ones (model doc §7) — and separately over the bet ones,
    so a gap between the two shows the filter is selecting the wrong rows."""
    picks = [pick(clv_pct=0.10, recommended=True), pick(clv_pct=-0.10, recommended=False)]
    report = summarize(picks, n_games_scored=2, n_games_excluded=0)
    assert report.clv.n == 2
    assert report.clv.avg_clv_pct == pytest.approx(0.0)
    assert report.clv_recommended.n == 1
    assert report.clv_recommended.avg_clv_pct == pytest.approx(0.10)


def test_empty_clv_summary_is_nan_not_zero() -> None:
    """Zero CLV means "the line never moved"; no picks means "no evidence"."""
    summary = clv_summary([])
    assert summary.n == 0
    assert math.isnan(summary.avg_clv_pct)


def test_calibration_excludes_pushes() -> None:
    picks = [pick(settlement="win"), pick(settlement="loss"), pick(settlement="push")]
    assert calibration_summary(picks).n == 2


def test_calibration_reports_ece_and_brier() -> None:
    picks = [pick(model_prob=0.65, settlement="win"), pick(model_prob=0.65, settlement="loss")]
    summary = calibration_summary(picks)
    assert summary.brier == pytest.approx((0.35**2 + 0.65**2) / 2)
    assert summary.ece == pytest.approx(0.15)
    assert [b.predicted_bucket for b in summary.buckets] == [6]


def test_roi_pays_the_price_that_was_taken() -> None:
    """+100 doubles the stake, so one win and one loss at even money nets zero."""
    picks = [pick(settlement="win", price=100), pick(settlement="loss", price=100)]
    summary = roi_summary(picks)
    assert summary.units_staked == pytest.approx(0.02)
    assert summary.units_won == pytest.approx(0.0)
    assert summary.roi_pct == pytest.approx(0.0)
    assert (summary.wins, summary.losses, summary.pushes) == (1, 1, 0)


def test_roi_returns_the_stake_on_a_push() -> None:
    summary = roi_summary([pick(settlement="push")])
    assert summary.units_staked == 0.0
    assert summary.units_won == 0.0
    assert summary.pushes == 1
    assert math.isnan(summary.roi_pct)


def test_roi_carries_its_noise_floor() -> None:
    """ROI is noise under ~2000 bets (CLAUDE.md), so the report says so rather
    than leaving a reader to guess."""
    assert ROI_MIN_BETS == 2000
    assert roi_summary([pick()]).above_noise_floor is False
    assert roi_summary([pick() for _ in range(ROI_MIN_BETS)]).above_noise_floor is True


def test_roi_covers_only_the_recommended_picks() -> None:
    """Evaluated-but-declined rows carry CLV, not stakes — you never bet them."""
    picks = [pick(recommended=True), pick(recommended=False)]
    report = summarize(picks, n_games_scored=2, n_games_excluded=0)
    assert report.roi.n_bets == 1
    assert report.clv.n == 2


def test_report_records_what_was_never_scored() -> None:
    report = summarize([pick()], n_games_scored=1, n_games_excluded=99)
    assert (report.n_games_scored, report.n_games_excluded) == (1, 99)
    assert len(report.picks) == 1
