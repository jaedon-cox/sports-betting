"""Fakes for the two things every job talks to: PostgREST and the wall clock.

Not a `conftest.py`: pytest imports conftest modules under their bare
basename when the test tree has no `__init__.py`, so a second one would
shadow `tests/unit/core/conftest.py` for the `from conftest import ...`
imports the core suite already uses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sbm.jobs.config import JobConfig
from sbm.jobs.context import JobContext


class FakeClient:
    """Records every call and answers RPCs from a scripted mapping.

    Deliberately not a mock library: the assertions that matter here are about
    *which table* a row went to and *which function* was called, and a recorded
    list reads better in a failure message than a call-args tuple.
    """

    def __init__(self, rpc_results: dict[str, Any] | None = None) -> None:
        self.inserts: list[tuple[str, list[dict]]] = []
        self.upserts: list[tuple[str, list[dict], str]] = []
        self.patches: list[tuple[str, dict, dict]] = []
        self.rpcs: list[tuple[str, dict]] = []
        self._rpc_results = rpc_results or {}
        self._next_id = 1

    def insert(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []  # mirrors PostgrestClient: no rows, no HTTP request
        self.inserts.append((table, rows))
        out = []
        for row in rows:
            out.append({**row, "id": self._next_id, "run_id": self._next_id})
            self._next_id += 1
        return out

    def upsert(
        self, table: str, rows: list[dict[str, Any]], on_conflict: str
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        self.upserts.append((table, rows, on_conflict))
        out = []
        for row in rows:
            out.append({**row, "id": self._next_id})
            self._next_id += 1
        return out

    def patch(self, table: str, match: dict[str, Any], values: dict[str, Any]) -> None:
        self.patches.append((table, match, values))

    def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
        self.rpcs.append((function_name, params))
        result = self._rpc_results.get(function_name, [])
        return result(params) if callable(result) else result

    def rows_for(self, table: str) -> list[dict[str, Any]]:
        return [row for name, rows in self.inserts if name == table for row in rows]


@dataclass
class FakeResponse:
    status_code: int = 200
    text: str = "{}"


@dataclass
class FakeHttp:
    """Minimal `httpx.Client` stand-in for the revalidate contract."""

    status_code: int = 200
    calls: list[dict[str, Any]] = field(default_factory=list)

    def post(self, url: str, *, headers: dict[str, str], json: Any = None) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(status_code=self.status_code)


def make_context(
    client: FakeClient | None = None,
    *,
    now: datetime | None = None,
    **config_overrides: Any,
) -> JobContext:
    env = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        "ODDS_API_KEY": "odds-key",
        "SITE_URL": "https://example.test",
        "REVALIDATE_SECRET": "shhh",
        **{k: str(v) for k, v in config_overrides.items()},
    }
    return JobContext(
        client=client or FakeClient(),  # type: ignore[arg-type]
        config=JobConfig.from_env(env),
        now=now or datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
    )
