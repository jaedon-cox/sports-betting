"""The publish handshake. web/README.md is authoritative on this contract."""

from __future__ import annotations

import pytest

from sbm.jobs.revalidate import (
    RevalidateError,
    revalidate,
    revalidate_publish,
    revalidate_settlement,
)
from tests.unit.jobs.fakes import FakeHttp


def test_secret_travels_in_the_header_and_nowhere_else() -> None:
    """A query-string secret ends up in referrer headers, proxy logs and browser
    history; a body secret is not what the endpoint reads."""
    http = FakeHttp()
    revalidate_publish("https://example.test", "shhh", client=http)
    call = http.calls[0]
    assert call["headers"]["x-revalidate-secret"] == "shhh"
    assert "shhh" not in call["url"]
    assert call["json"] is None  # empty body == "a slate published"


def test_publish_sends_no_body_and_settlement_sends_its_two_tags() -> None:
    http = FakeHttp()
    revalidate_settlement("https://example.test/", "shhh", client=http)
    assert http.calls[0]["url"] == "https://example.test/api/revalidate"
    assert http.calls[0]["json"] == {"tags": ["record", "archive"]}


def test_an_unknown_tag_fails_here_rather_than_as_a_400_in_production() -> None:
    with pytest.raises(RevalidateError, match="unknown revalidate tag"):
        revalidate("https://example.test", "shhh", tags=("slat",), client=FakeHttp())


def test_a_rejected_purge_raises() -> None:
    """A swallowed failure means the site serves a stale slate indefinitely,
    which looks exactly like a working site."""
    with pytest.raises(RevalidateError, match="401"):
        revalidate_publish("https://example.test", "wrong", client=FakeHttp(status_code=401))
