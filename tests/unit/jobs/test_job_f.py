"""Job F end to end over fakes — the four things the Record page needs."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sbm.jobs import job_f_settlement
from sbm.jobs.job_f_settlement import run
from tests.unit.jobs.fakes import FakeClient, FakeHttp, make_context
from tests.unit.jobs.test_odds_sweep import game, make_slate

NOW = datetime(2026, 7, 2, 8, 0, tzinfo=UTC)  # 04:00 ET, the intended trigger


def unsettled_row(pick_id: int, **overrides: object) -> dict:
    base = {
        "pick_id": pick_id, "game_id": 101, "market": "moneyline", "side": "home",
        "line": None, "bet_prob": 0.50, "model_prob": 0.55, "game_status": "final",
        "home_score": 5, "away_score": 3, "game_date": "2026-07-01",
        "closing_prob": 0.55, "closing_line": None,
    }
    return {**base, **overrides}


@pytest.fixture
def wired(monkeypatch):
    finished = game(1, "Yankees", "Red Sox")
    slate = make_slate(
        [
            type(finished)(
                **{
                    **{f: getattr(finished, f) for f in finished.__slots__},
                    "status": "final", "home_score": 5, "away_score": 3,
                }
            )
        ]
    )
    monkeypatch.setattr(job_f_settlement, "ingest_slate", lambda *a, **k: slate)
    monkeypatch.setattr(job_f_settlement, "StatsApiClient", lambda: _NullClient())
    http = FakeHttp()
    monkeypatch.setattr(job_f_settlement, "revalidate_settlement",
                        lambda url, secret: http.post(url, headers={"x-revalidate-secret": secret}))
    return http


class _NullClient:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def test_job_f_records_results_settles_rolls_up_and_purges(wired) -> None:
    client = FakeClient(
        rpc_results={
            "fn_record_results": 1,
            "fn_unsettled_picks": [unsettled_row(1), unsettled_row(2, side="away")],
            "fn_settled_picks_for_date": [
                {"market": "moneyline", "model_prob": 0.55, "outcome": "win"},
                {"market": "moneyline", "model_prob": 0.45, "outcome": "loss"},
            ],
            "fn_refresh_rollups": None,
        }
    )
    summary = run(make_context(client, now=NOW))

    called = [name for name, _ in client.rpcs]
    assert "fn_record_results" in called
    assert "fn_refresh_rollups" in called, "the three matviews must be refreshed"

    settlements = client.rows_for("pick_settlements")
    assert {row["outcome"] for row in settlements} == {"win", "loss"}
    assert settlements[0]["clv_pct"] == pytest.approx(0.1)  # relative, per core.clv

    buckets = [u for u in client.upserts if u[0] == "calibration_buckets"]
    assert buckets, "calibration_buckets is a physical table and must be UPSERTed"
    assert buckets[0][2] == "rollup_date,sport,market,predicted_bucket,method_version"
    assert {row["predicted_bucket"] for row in buckets[0][1]} == {5, 6}

    assert wired.calls[0]["headers"]["x-revalidate-secret"] == "shhh"
    assert "matviews refreshed" in summary


def test_calibration_rollup_covers_every_date_the_night_touched(wired) -> None:
    """A postponed game settled weeks later must roll up its *own* slate date,
    not tonight's."""
    client = FakeClient(
        rpc_results={
            "fn_record_results": 0,
            "fn_unsettled_picks": [
                unsettled_row(1),
                unsettled_row(2, game_date="2026-06-20"),
            ],
            "fn_settled_picks_for_date": [],
            "fn_refresh_rollups": None,
        }
    )
    run(make_context(client, now=NOW))
    dates = [p["p_rollup_date"] for name, p in client.rpcs if name == "fn_settled_picks_for_date"]
    assert sorted(dates) == ["2026-06-20", "2026-07-01"]


def test_an_unsettled_night_still_refreshes_nothing_stale(wired) -> None:
    client = FakeClient(
        rpc_results={"fn_record_results": 0, "fn_unsettled_picks": [], "fn_refresh_rollups": None}
    )
    summary = run(make_context(client, now=NOW))
    assert client.rows_for("pick_settlements") == []
    assert "fn_refresh_rollups" in [name for name, _ in client.rpcs]
    assert "0 settlements" in summary


def test_the_guard_targets_four_am_et() -> None:
    assert job_f_settlement.guard(make_context(now=NOW)) is True
    assert job_f_settlement.guard(make_context(now=NOW.replace(hour=9))) is False
