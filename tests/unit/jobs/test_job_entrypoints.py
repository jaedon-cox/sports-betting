"""Job A end-to-end over fakes, the shared wiring, and the three DST guards.

The per-step logic is tested in its own module; what this covers is the
*composition* — which of the four side effects (slate status, raw archive, ISR
purge, publish) the daily pull performs on each branch. Those are the parts a
refactor silently breaks, because every one is a call whose absence looks
exactly like a working job. `test_jobs_c_and_d.py` covers the two model passes
and imports `slate`/`wire` from here.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, date, datetime

import pytest

from sbm.jobs import job_a_daily_pull, job_c_projected, job_d_confirmed
from sbm.jobs.odds_sweep import SweepResult
from sbm.jobs.slate_ingest import Slate
from sbm.odds.resolution import NOT_INGESTED
from tests.unit.jobs.fakes import FakeClient, make_context
from tests.unit.jobs.test_odds_sweep import game

NOW = datetime(2026, 7, 1, 22, 45, tzinfo=UTC)
SLATE_DATE = date(2026, 7, 1)


def slate(*pks: int) -> Slate:
    games = [game(pk, "HOM", "AWY") for pk in pks]
    return Slate(
        slate_date=SLATE_DATE,
        games=games,
        game_ids={str(pk): 100 + i for i, pk in enumerate(pks)},
        team_ids={1: 11, 2: 22},
    )


@contextlib.contextmanager
def _null_stats():
    yield object()


def wire(monkeypatch, module, *, returned: Slate) -> dict:
    """Neutralise every network edge a job entrypoint has, recording the calls.

    `ingest_slate`, the StatsAPI client and the ISR purge are the three every
    job shares; the caller patches whatever else its branch reaches.
    """
    calls: dict = {"revalidate": 0, "status": []}
    monkeypatch.setattr(module, "StatsApiClient", lambda *a, **k: _null_stats())
    monkeypatch.setattr(module, "ingest_slate", lambda *a, **k: returned)
    if hasattr(module, "revalidate_publish"):
        monkeypatch.setattr(
            module, "revalidate_publish",
            lambda *a, **k: calls.__setitem__("revalidate", calls["revalidate"] + 1),
        )
    if hasattr(module, "write_slate_status"):
        monkeypatch.setattr(
            module, "write_slate_status",
            lambda client, **kw: calls["status"].append(kw),
        )
    return calls


# --------------------------------------------------------------------------
# Job A
# --------------------------------------------------------------------------


def wire_job_a(monkeypatch, *, returned: Slate, result: SweepResult | None = None) -> dict:
    calls = wire(monkeypatch, job_a_daily_pull, returned=returned)
    monkeypatch.setattr(job_a_daily_pull, "pull_weather", lambda *a, **k: 3)
    monkeypatch.setattr(job_a_daily_pull, "drain", lambda *a, **k: 2)
    monkeypatch.setattr(
        job_a_daily_pull, "sweep",
        lambda *a, **k: result or SweepResult(rows_written=6, closing_rows=0, skipped_by_reason={}, credits=3),
    )
    return calls


def test_an_off_day_publishes_no_games_rather_than_an_empty_page(monkeypatch) -> None:
    """The frontend otherwise cannot tell an off-day from a pipeline that died
    before the schedule pull (`slate.py`)."""
    calls = wire_job_a(monkeypatch, returned=slate())
    summary = job_a_daily_pull.run(make_context(FakeClient(), now=NOW))
    assert calls["status"] == [
        {"sport": "mlb", "slate_date": SLATE_DATE, "status": "no_games", "n_games": 0}
    ]
    assert calls["revalidate"] == 1
    assert "no games" in summary


def test_an_off_day_buys_no_odds_credits(monkeypatch) -> None:
    """The tightest constraint in the system (§2.5) — an empty slate must not
    spend three of 500."""
    spent: list[int] = []
    monkeypatch.setattr(job_a_daily_pull, "sweep", lambda *a, **k: spent.append(1))
    wire(monkeypatch, job_a_daily_pull, returned=slate())
    monkeypatch.setattr(job_a_daily_pull, "drain", lambda *a, **k: 0)
    job_a_daily_pull.run(make_context(FakeClient(), now=NOW))
    assert spent == []


def test_a_normal_day_marks_the_slate_pending_not_published(monkeypatch) -> None:
    """Job A pulls the board; only Job D's confirmed pass publishes it."""
    calls = wire_job_a(monkeypatch, returned=slate(555, 556))
    job_a_daily_pull.run(make_context(FakeClient(), now=NOW))
    assert calls["status"][0]["status"] == "pending"
    assert calls["status"][0]["n_games"] == 2
    assert "model_run_id" not in calls["status"][0]


def test_slate_integrity_is_asserted_after_the_lines_are_already_stored(monkeypatch) -> None:
    """A gamePk the odds feed knows and `games` does not is a broken join, but
    the six line rows already bought are worth keeping."""
    calls = wire_job_a(
        monkeypatch,
        returned=slate(555),
        result=SweepResult(rows_written=6, closing_rows=0, skipped_by_reason={NOT_INGESTED: 1}, credits=3),
    )
    with pytest.raises(Exception):
        job_a_daily_pull.run(make_context(FakeClient(), now=NOW))
    assert calls["status"][0]["status"] == "pending"  # written before the raise
    assert calls["revalidate"] == 1


# --------------------------------------------------------------------------
# the DST guards
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("module", "et_hour", "et_minute"),
    [(job_a_daily_pull, 8, 0), (job_c_projected, 16, 0), (job_d_confirmed, 18, 15)],
)
def test_each_guard_admits_exactly_its_own_et_instant(module, et_hour, et_minute) -> None:
    """Two crons fire per ET target so DST cannot shift the hour; the guard is
    what drops the one that is not intended (`clock.py`)."""
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    intended = datetime(2026, 7, 1, et_hour, et_minute, tzinfo=et).astimezone(UTC)
    assert module.guard(make_context(now=intended)) is True
    assert module.guard(make_context(now=intended.replace(hour=intended.hour - 1))) is False
