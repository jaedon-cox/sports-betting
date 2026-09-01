"""Job F: grading, CLV nulls, and the calibration buckets the Record page needs."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from sbm.jobs.job_f_settlement.outcomes import settle_picks, write_settlements
from sbm.jobs.job_f_settlement.rollups import METHOD_VERSION, bucket_rows, decile
from sbm.jobs.rpc import SettledPick, UnsettledPick
from sbm.markets import market_registry
from tests.unit.jobs.fakes import FakeClient

MARKETS = market_registry()


def pick(**overrides: object) -> UnsettledPick:
    base = dict(
        pick_id=1, game_id=10, market="moneyline", side="home", line=None,
        bet_prob=0.50, model_prob=0.55, game_status="final",
        home_score=5, away_score=3, game_date=date(2026, 7, 1),
        closing_prob=0.55, closing_line=None,
    )
    return UnsettledPick(**{**base, **overrides})  # type: ignore[arg-type]


def test_settlement_replays_the_market_plugin_over_the_final_score() -> None:
    """No per-market settlement branch: adding a market adds no code here."""
    rows = settle_picks([pick(), pick(pick_id=2, side="away")], MARKETS)
    assert [row.outcome for row in rows] == ["win", "loss"]


def test_clv_is_relative_and_matches_core() -> None:
    """`(closing_prob - bet_prob) / bet_prob` — the settlement unit, not the
    absolute one `v_pick_clv_live` reports (web/README "Two CLV units")."""
    row = settle_picks([pick(bet_prob=0.50, closing_prob=0.55)], MARKETS)[0]
    assert row.clv_pct == pytest.approx(0.1)
    assert (row.bet_prob, row.closing_prob) == (0.50, 0.55)


def test_a_missing_close_is_a_null_row_never_a_raise() -> None:
    """A postponed game, a sweep skipped for budget (§2.5), or a missed window —
    fabricating a close to fill this would corrupt the gate metric silently."""
    row = settle_picks([pick(closing_prob=None)], MARKETS)[0]
    assert row.outcome == "win"
    assert row.clv_pct is None and row.closing_prob is None


def test_postponed_and_cancelled_games_are_void_with_no_clv() -> None:
    """'void' is a scheduling fact a result row cannot express — `settle` says so
    itself, which is why those games are graded here rather than passed to it."""
    for status in ("postponed", "cancelled"):
        row = settle_picks([pick(game_status=status, home_score=None, away_score=None)], MARKETS)[0]
        assert (row.outcome, row.clv_pct, row.closing_prob) == ("void", None, None)


def test_in_progress_games_are_left_for_the_next_night() -> None:
    """Settlement is keyed on the absence of a settlement row, so waiting loses
    nothing."""
    assert settle_picks([pick(game_status="in_progress", home_score=None)], MARKETS) == []


def test_a_push_is_graded_as_a_push() -> None:
    row = settle_picks(
        [pick(market="total", side="over", line=8.0, home_score=5, away_score=3)], MARKETS
    )[0]
    assert row.outcome == "push"


def test_settlements_are_a_plain_insert_into_the_append_only_table() -> None:
    client = FakeClient()
    assert write_settlements(client, settle_picks([pick()], MARKETS)) == 1  # type: ignore[arg-type]
    table, rows = client.inserts[0]
    assert table == "pick_settlements"
    assert set(rows[0]) == {"pick_id", "outcome", "bet_prob", "closing_prob", "clv_pct"}


def test_deciles_match_width_bucket_including_the_endpoint() -> None:
    """`width_bucket(p, 0, 1, 10)` puts 1.0 in an 11th bucket; the CHECK is
    BETWEEN 1 AND 10, so the clamp lives here."""
    assert [decile(p) for p in (0.0, 0.05, 0.1, 0.55, 0.99, 1.0)] == [1, 1, 2, 6, 10, 10]


def test_buckets_drop_pushes_and_voids() -> None:
    """A push is not a binary outcome; scoring it as a loss would teach the
    calibrator to shade every probability down."""
    settled = [
        SettledPick("moneyline", 0.62, "win"),
        SettledPick("total", 0.65, "loss"),
        SettledPick("moneyline", 0.61, "push"),
        SettledPick("spread", 0.68, "void"),
    ]
    rows = bucket_rows(settled, sport="mlb", rollup_date=date(2026, 7, 1))
    assert len(rows) == 1
    row = rows[0]
    assert (row["predicted_bucket"], row["n"], row["actual_win_rate"]) == (7, 2, 0.5)
    assert row["market"] == "blended" and row["method_version"] == METHOD_VERSION
    assert row["avg_predicted_prob"] == 0.635


def test_a_date_with_only_unscoreable_outcomes_writes_no_bucket() -> None:
    rows = bucket_rows([SettledPick("moneyline", 0.5, "void")], sport="mlb", rollup_date=date(2026, 7, 1))
    assert rows == []


def test_settlement_rows_carry_the_pick_id_the_upsert_key_needs() -> None:
    now = datetime(2026, 7, 2, 8, tzinfo=UTC)
    assert now.tzinfo is UTC  # the job passes an aware instant through
    assert settle_picks([pick(pick_id=99)], MARKETS)[0].pick_id == 99
