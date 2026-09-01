"""The pipeline_runs pair, and who the DST guard is allowed to stop."""

from __future__ import annotations

from sbm.jobs.runner import execute
from tests.unit.jobs.fakes import FakeClient, make_context


def test_success_writes_a_start_row_and_flips_it(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    client = FakeClient()
    assert execute("job_x", lambda ctx: "done", ctx=make_context(client)) == 0
    assert client.inserts[0][0] == "pipeline_runs"
    assert client.inserts[0][1][0]["status"] == "running"
    table, match, values = client.patches[0]
    assert (table, values["status"], values["error_message"]) == ("pipeline_runs", "success", None)


def test_a_failure_still_reaches_the_health_table() -> None:
    client = FakeClient()

    def boom(ctx: object) -> str:
        raise ValueError("upstream shape changed")

    assert execute("job_x", boom, ctx=make_context(client)) == 1
    _, _, values = client.patches[0]
    assert values["status"] == "failed"
    assert "upstream shape changed" in values["error_message"]


def test_a_guarded_out_trigger_writes_no_row_at_all(monkeypatch) -> None:
    """One `pipeline_runs` row per skipped DST duplicate would double the table
    and make "did Job A run today?" unanswerable by a count."""
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    client = FakeClient()
    calls: list[int] = []
    code = execute(
        "job_x",
        lambda ctx: calls.append(1) or "ran",  # type: ignore[func-returns-value]
        guard=lambda ctx: False,
        ctx=make_context(client),
    )
    assert code == 0
    assert client.inserts == [] and client.patches == [] and calls == []


def test_manual_dispatch_ignores_the_guard(monkeypatch) -> None:
    """An operator re-running a job is doing it at the wrong hour on purpose."""
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    client = FakeClient()
    assert execute("job_x", lambda ctx: "ran", guard=lambda ctx: False, ctx=make_context(client)) == 0
    assert client.inserts[0][0] == "pipeline_runs"


def test_a_scheduled_trigger_honours_the_guard(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    client = FakeClient()
    assert execute("job_x", lambda ctx: "ran", guard=lambda ctx: False, ctx=make_context(client)) == 0
    assert client.inserts == []
