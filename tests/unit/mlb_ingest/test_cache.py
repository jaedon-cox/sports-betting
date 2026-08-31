"""fetch_with_disk_cache must fall back to a stale cache on fetch failure,
and must fail loud only when there's truly nothing to fall back to."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from sbm.sports.mlb.ingest.cache import IngestSourceError, fetch_with_disk_cache

FIRST = pd.DataFrame({"siera": [3.1, 3.5]})
SECOND = pd.DataFrame({"siera": [3.2, 3.6]})


def test_fresh_fetch_is_not_stale_and_is_cached(tmp_path: Path) -> None:
    path = tmp_path / "pitching.csv"
    result = fetch_with_disk_cache(path, lambda: FIRST, now=datetime(2026, 8, 29, tzinfo=UTC))
    assert result.is_stale is False
    pd.testing.assert_frame_equal(result.frame, FIRST)
    assert path.exists()


def test_failed_fetch_falls_back_to_prior_cache_and_flags_stale(tmp_path: Path) -> None:
    path = tmp_path / "pitching.csv"
    fetch_with_disk_cache(path, lambda: FIRST, now=datetime(2026, 8, 28, tzinfo=UTC))

    def failing_fetch() -> pd.DataFrame:
        raise RuntimeError("upstream site changed shape")

    result = fetch_with_disk_cache(path, failing_fetch, now=datetime(2026, 8, 29, tzinfo=UTC))
    assert result.is_stale is True
    assert result.fetched_at_utc == datetime(2026, 8, 28, tzinfo=UTC)
    pd.testing.assert_frame_equal(result.frame, FIRST)


def test_failed_fetch_with_no_prior_cache_raises() -> None:
    def failing_fetch() -> pd.DataFrame:
        raise RuntimeError("boom")

    with pytest.raises(IngestSourceError):
        fetch_with_disk_cache(Path("/nonexistent/does-not-exist.csv"), failing_fetch)


def test_a_second_fresh_fetch_overwrites_the_cache(tmp_path: Path) -> None:
    path = tmp_path / "pitching.csv"
    fetch_with_disk_cache(path, lambda: FIRST, now=datetime(2026, 8, 28, tzinfo=UTC))
    result = fetch_with_disk_cache(path, lambda: SECOND, now=datetime(2026, 8, 29, tzinfo=UTC))
    assert result.is_stale is False
    pd.testing.assert_frame_equal(result.frame, SECOND)


def test_max_age_skips_the_network_call_when_cache_is_fresh_enough(tmp_path: Path) -> None:
    path = tmp_path / "pitching.csv"
    calls = {"n": 0}

    def counting_fetch() -> pd.DataFrame:
        calls["n"] += 1
        return FIRST if calls["n"] == 1 else SECOND

    morning = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    afternoon = datetime(2026, 8, 29, 14, 0, tzinfo=UTC)  # 6h later, both same day

    fetch_with_disk_cache(path, counting_fetch, now=morning, max_age=timedelta(hours=20))
    result = fetch_with_disk_cache(path, counting_fetch, now=afternoon, max_age=timedelta(hours=20))

    assert calls["n"] == 1  # second call read the cache, never invoked fetch again
    assert result.is_stale is False
    pd.testing.assert_frame_equal(result.frame, FIRST)


def test_max_age_expired_triggers_a_fresh_fetch(tmp_path: Path) -> None:
    path = tmp_path / "pitching.csv"
    fetch_with_disk_cache(path, lambda: FIRST, now=datetime(2026, 8, 28, tzinfo=UTC), max_age=timedelta(hours=20))
    result = fetch_with_disk_cache(
        path, lambda: SECOND, now=datetime(2026, 8, 29, tzinfo=UTC), max_age=timedelta(hours=20)
    )
    assert result.is_stale is False
    pd.testing.assert_frame_equal(result.frame, SECOND)
