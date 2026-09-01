"""Push-based ISR invalidation — the publish handshake's last step (§2.3, §5).

The frontend caches Supabase reads in Next's Data Cache and never polls, so a
slate that publishes without this call is invisible until the cache expires on
its own. `web/README.md` is authoritative on the contract; the two call shapes
below are its two copyable curls.

**The secret travels in `x-revalidate-secret` and nowhere else** — never a
query string, never the body. A query-string secret ends up in referrer
headers, proxy logs and browser history, and the endpoint compares it in
constant time on the other side.

An unrecognised tag is a 400 rather than a silent no-op, which is why
`TAGS` mirrors the frontend's table here: a typo should fail in review, not in
production at 3am. Raising `RevalidateError` on any non-2xx is the same
principle one level up — a swallowed purge failure means the site serves a
stale slate indefinitely, which looks exactly like a working site.
"""

from __future__ import annotations

import httpx

TAGS = frozenset({"slate", "archive", "record", "reference"})
"""The tags `web/api/revalidate` accepts. Anything else is a 400."""

SETTLEMENT_TAGS = ("record", "archive")
"""Job F: rollups changed and outcomes landed on existing picks."""

_TIMEOUT = 15.0


class RevalidateError(RuntimeError):
    """The frontend did not accept the purge."""


def revalidate(
    site_url: str,
    secret: str,
    *,
    tags: tuple[str, ...] = (),
    client: httpx.Client | None = None,
) -> None:
    """POST the purge. Empty `tags` means "a slate published" (slate + archive).

    Sending no body for the publish case is deliberate rather than lazy: it is
    the documented default the endpoint is built around, so the common path
    exercises the same branch the frontend's own tests do.
    """
    unknown = sorted(set(tags) - TAGS)
    if unknown:
        raise RevalidateError(f"unknown revalidate tag(s) {unknown}; the endpoint answers 400")

    url = site_url.rstrip("/") + "/api/revalidate"
    headers = {"x-revalidate-secret": secret}
    body: dict[str, list[str]] | None = None
    if tags:
        headers["content-type"] = "application/json"
        body = {"tags": list(tags)}

    owns_client = client is None
    http = client or httpx.Client(timeout=_TIMEOUT)
    try:
        resp = http.post(url, headers=headers, json=body)
    finally:
        if owns_client:
            http.close()
    if resp.status_code >= 400:
        raise RevalidateError(
            f"revalidate returned {resp.status_code} for tags={list(tags) or ['<default>']}: "
            f"{resp.text[:200]}"
        )


def revalidate_publish(site_url: str, secret: str, *, client: httpx.Client | None = None) -> None:
    """After a successful publish: the Today's Picks board and the archive."""
    revalidate(site_url, secret, client=client)


def revalidate_settlement(site_url: str, secret: str, *, client: httpx.Client | None = None) -> None:
    """After Job F: rollups refreshed, outcomes written."""
    revalidate(site_url, secret, tags=SETTLEMENT_TAGS, client=client)
