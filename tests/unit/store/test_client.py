"""`PostgrestClient.rpc` and the two response shapes PostgREST actually sends.

A function declared `RETURNS VOID` comes back as `204 No Content` with a
zero-length body. That passes `raise_for_status` and then dies in `.json()`
with a bare `JSONDecodeError: Expecting value: line 1 column 1` — an error
naming neither the function nor the cause. `fn_refresh_rollups` is the only
such function today and Job F calls it on every run, so the empty-body path is
as load-bearing as the JSON one.

`tests/unit/jobs/fakes.py`'s FakeClient answers every RPC with a JSON value, so
it cannot surface this; that is why the check lives down here against the real
client instead.
"""

from __future__ import annotations

import httpx
import pytest

from sbm.store.client import PostgrestClient

URL = "https://example.supabase.co"
KEY = "service-key"


def client() -> PostgrestClient:
    return PostgrestClient(base_url=URL, service_key=KEY)


def respond(monkeypatch, response: httpx.Response) -> list[dict]:
    """Capture the outgoing request and answer it with `response`."""
    seen: list[dict] = []

    def fake_post(url, *, json=None, headers=None, timeout=None):
        seen.append({"url": url, "json": json, "headers": headers})
        return response

    monkeypatch.setattr(httpx, "post", fake_post)
    return seen


def response(status: int, *, body: bytes = b"", json_body=None) -> httpx.Response:
    request = httpx.Request("POST", f"{URL}/rest/v1/rpc/fn")
    if json_body is not None:
        return httpx.Response(status, json=json_body, request=request)
    return httpx.Response(status, content=body, request=request)


def test_a_void_function_returns_none_rather_than_raising(monkeypatch) -> None:
    """The production failure: Job F died on its last step, after results,
    settlements and calibration buckets had all been written."""
    respond(monkeypatch, response(204))
    assert client().rpc("fn_refresh_rollups", {}) is None


def test_a_200_with_an_empty_body_is_also_treated_as_no_content(monkeypatch) -> None:
    """Belt and braces — the guard keys on emptiness as well as on the status,
    so a proxy that rewrites 204 to 200 cannot resurrect the crash."""
    respond(monkeypatch, response(200, body=b""))
    assert client().rpc("fn_refresh_rollups", {}) is None


def test_a_scalar_return_still_parses(monkeypatch) -> None:
    """`fn_publish_run` returns the model_run id, and Job C/D depend on it."""
    respond(monkeypatch, response(200, json_body=42))
    assert client().rpc("fn_publish_run", {"p_sport": "mlb"}) == 42


def test_a_table_return_still_parses(monkeypatch) -> None:
    respond(monkeypatch, response(200, json_body=[{"game_id": 1}, {"game_id": 2}]))
    rows = client().rpc("fn_latest_lines", {})
    assert [r["game_id"] for r in rows] == [1, 2]


def test_an_error_status_still_raises(monkeypatch) -> None:
    """An empty body must not turn a 500 into a silent None."""
    respond(monkeypatch, response(500, body=b""))
    with pytest.raises(httpx.HTTPStatusError):
        client().rpc("fn_refresh_rollups", {})


def test_the_function_is_called_under_rest_v1_rpc(monkeypatch) -> None:
    """`base_url` is the bare project URL; the client appends the REST path."""
    seen = respond(monkeypatch, response(204))
    client().rpc("fn_refresh_rollups", {"p_sport": "mlb"})
    assert seen[0]["url"] == f"{URL}/rest/v1/rpc/fn_refresh_rollups"
    assert seen[0]["json"] == {"p_sport": "mlb"}
    assert seen[0]["headers"]["Authorization"] == f"Bearer {KEY}"
