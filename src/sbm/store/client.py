"""Thin PostgREST client — the only way this package talks to Postgres.

No native Postgres driver, and therefore no new dependency beyond the
httpx already in pyproject.toml (CLAUDE.md: "no new dependency without a
note in the PR body" — this is the note). Every write goes over
Supabase's PostgREST HTTP API using the service-role key, which bypasses
RLS (§5). Where an operation must be atomic across multiple tables (the
day's slate of picks + the model_runs status flip, §2.4), that atomicity
comes from calling a single Postgres function via `rpc()` — a function
body is one implicit transaction — not from a client-managed
BEGIN/COMMIT, which PostgREST doesn't support across separate requests.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

_TIMEOUT = 15.0


class PostgrestClient:
    """Authenticated wrapper around one Supabase project's REST endpoint."""

    def __init__(self, base_url: str | None = None, service_key: str | None = None) -> None:
        base_url = base_url or os.environ["SUPABASE_URL"]
        service_key = service_key or os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        self._rest_url = base_url.rstrip("/") + "/rest/v1"
        self._headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

    def insert(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Plain INSERT — the only write mode for append-only tables."""
        if not rows:
            return []
        resp = httpx.post(
            f"{self._rest_url}/{table}",
            json=rows,
            headers={**self._headers, "Prefer": "return=representation"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def upsert(self, table: str, rows: list[dict[str, Any]], on_conflict: str) -> list[dict[str, Any]]:
        """UPSERT for the handful of mutable reference/fact tables
        (games, teams) — never for an append-only table."""
        if not rows:
            return []
        resp = httpx.post(
            f"{self._rest_url}/{table}?on_conflict={on_conflict}",
            json=rows,
            headers={**self._headers, "Prefer": "resolution=merge-duplicates,return=representation"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def patch(self, table: str, match: dict[str, Any], values: dict[str, Any]) -> None:
        """UPDATE the row(s) matching `match` (exact-match filters only).
        Used only where the schema explicitly allows a mutation —
        pipeline_runs status transitions today."""
        params = {key: f"eq.{value}" for key, value in match.items()}
        resp = httpx.patch(
            f"{self._rest_url}/{table}", params=params, json=values, headers=self._headers, timeout=_TIMEOUT
        )
        resp.raise_for_status()

    def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
        """Call a Postgres function — the one way this layer gets a
        multi-statement operation to run as a single transaction.

        Returns None for a function declared `RETURNS VOID`: PostgREST answers
        those with `204 No Content` and a zero-length body, which passes
        `raise_for_status` and then fails in `resp.json()` as a bare
        `JSONDecodeError: Expecting value: line 1 column 1` — an error that
        names neither the function nor the reason. `fn_refresh_rollups` is the
        only such function today (db/migrations/011), and Job F calls it on
        every settlement run, so this is the difference between a nightly job
        that completes and one that dies on its last step.
        """
        resp = httpx.post(f"{self._rest_url}/rpc/{function_name}", json=params, headers=self._headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()
