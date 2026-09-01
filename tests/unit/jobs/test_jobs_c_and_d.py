"""Jobs C and D: the research pass and the official pick.

They share `model_pass.run_pass` entirely, so what separates them is the four
things only Job D does — write `slate_status`, carry the run id that produced
it, purge the frontend cache, and record `failed` when the pass raises. Each
test below is one of those differences. Helpers come from
`test_job_entrypoints.py`, which covers Job A and the shared wiring.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from sbm.jobs import job_c_projected, job_d_confirmed
from sbm.jobs.model_pass import PassResult
from sbm.jobs.slate_ingest import Slate
from tests.unit.jobs.fakes import FakeClient, make_context
from tests.unit.jobs.test_job_entrypoints import slate, wire

NOW = datetime(2026, 7, 1, 22, 45, tzinfo=UTC)
SLATE_DATE = date(2026, 7, 1)


def test_job_c_writes_no_slate_status_and_fires_no_revalidation(monkeypatch) -> None:
    """`v_todays_picks` filters strictly to pass_type='confirmed', so nothing
    Job C publishes reaches a view the frontend reads."""
    assert not hasattr(job_c_projected, "write_slate_status")
    assert not hasattr(job_c_projected, "revalidate_publish")


def test_job_c_publishes_under_the_projected_pass_type(monkeypatch) -> None:
    seen: dict = {}

    def fake_pass(ctx, slate_arg, *, pass_type, **kwargs):
        seen["pass_type"] = pass_type
        return PassResult(7, len(slate_arg.games), 4, 2, {})

    wire(monkeypatch, job_c_projected, returned=slate(555))
    monkeypatch.setattr(job_c_projected, "drain", lambda *a, **k: 0)
    monkeypatch.setattr(job_c_projected, "run_pass", fake_pass)
    summary = job_c_projected.run(make_context(FakeClient(), now=NOW))
    assert seen["pass_type"] == "projected"
    assert "pass=projected" in summary and "run=7" in summary


def test_job_c_on_an_empty_slate_scores_nothing(monkeypatch) -> None:
    wire(monkeypatch, job_c_projected, returned=slate())
    monkeypatch.setattr(job_c_projected, "drain", lambda *a, **k: 0)
    monkeypatch.setattr(
        job_c_projected, "run_pass",
        lambda *a, **k: pytest.fail("an empty slate must not reach the model"),
    )
    assert "no games" in job_c_projected.run(make_context(FakeClient(), now=NOW))


# --------------------------------------------------------------------------
# Job D — the official pick
# --------------------------------------------------------------------------


def wire_job_d(monkeypatch, *, returned: Slate, passes) -> dict:
    calls = wire(monkeypatch, job_d_confirmed, returned=returned)
    monkeypatch.setattr(job_d_confirmed, "drain", lambda *a, **k: 0)
    monkeypatch.setattr(job_d_confirmed, "run_pass", passes)
    return calls


def test_a_published_slate_carries_the_run_id_that_produced_it(monkeypatch) -> None:
    """That id is what lets the frontend read the publish time from
    `model_runs.updated_at` — the "generated at HH:MM ET" banner."""
    calls = wire_job_d(
        monkeypatch, returned=slate(555, 556),
        passes=lambda ctx, s, **k: PassResult(42, 2, 5, 3, {}),
    )
    job_d_confirmed.run(make_context(FakeClient(), now=NOW))
    assert calls["status"] == [
        {
            "sport": "mlb", "slate_date": SLATE_DATE, "status": "published",
            "n_games": 2, "model_run_id": 42,
        }
    ]
    assert calls["revalidate"] == 1


def test_a_failed_pass_records_failed_and_re_raises(monkeypatch) -> None:
    """The frontend must tell "today failed" from "today is still coming"; only
    `slate_status` is a view the board reads."""

    def boom(ctx, s, **k):
        raise RuntimeError("scoring blew up")

    calls = wire_job_d(monkeypatch, returned=slate(555), passes=boom)
    with pytest.raises(RuntimeError, match="scoring blew up"):
        job_d_confirmed.run(make_context(FakeClient(), now=NOW))
    assert calls["status"][0]["status"] == "failed"
    assert "model_run_id" not in calls["status"][0]  # nothing published to point at


def test_a_failed_pass_does_not_purge_the_frontend_cache(monkeypatch) -> None:
    """Purging would replace the last known-good slate with nothing, which is
    the exact thing atomic publish exists to prevent (§2.4)."""

    def boom(ctx, s, **k):
        raise RuntimeError("nope")

    calls = wire_job_d(monkeypatch, returned=slate(555), passes=boom)
    with pytest.raises(RuntimeError):
        job_d_confirmed.run(make_context(FakeClient(), now=NOW))
    assert calls["revalidate"] == 0


def test_job_d_publishes_under_the_confirmed_pass_type(monkeypatch) -> None:
    seen: dict = {}

    def fake_pass(ctx, s, *, pass_type, **kwargs):
        seen["pass_type"] = pass_type
        return PassResult(1, 1, 1, 1, {})

    wire_job_d(monkeypatch, returned=slate(555), passes=fake_pass)
    job_d_confirmed.run(make_context(FakeClient(), now=NOW))
    assert seen["pass_type"] == "confirmed"


def test_an_off_day_marks_no_games_and_never_reaches_the_model(monkeypatch) -> None:
    calls = wire_job_d(
        monkeypatch, returned=slate(),
        passes=lambda *a, **k: pytest.fail("an empty slate must not reach the model"),
    )
    assert "no games" in job_d_confirmed.run(make_context(FakeClient(), now=NOW))
    assert calls["status"][0]["status"] == "no_games"
