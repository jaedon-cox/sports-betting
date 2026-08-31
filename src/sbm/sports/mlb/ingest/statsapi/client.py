"""Throttled HTTP wrapper around MLB StatsAPI — unofficial, no SLA (backend
doc §2.1, ingest task 4: self-throttle to <=1 req/s).

Shape-drift handling is the *caller's* job (each field access downstream uses
`.get()` with a default), not this module's — `StatsApiClient` only fetches
and parses JSON.
"""

from __future__ import annotations

from types import TracebackType

import httpx

from sbm.sports.mlb.ingest.throttle import Throttle

BASE_URL = "https://statsapi.mlb.com/api/v1"


class StatsApiClient:
    """Inject an `httpx.Client` (e.g. one backed by `httpx.MockTransport`) to
    keep ingest code offline-testable; the default constructs a real one."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        throttle: Throttle | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=10.0)
        self._throttle = throttle or Throttle(min_interval_s=1.0)

    def get(self, path: str, params: dict | None = None) -> dict:
        self._throttle.wait()
        resp = self._client.get(f"{BASE_URL}{path}", params=params or {})
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> StatsApiClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
