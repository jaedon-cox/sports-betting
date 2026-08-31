"""Disk cache with stale-fallback for scraping-based sources (pybaseball,
Savant — backend doc §2.1: "1x/day, prior-day batch, disk-cached").

Two jobs in one: (1) avoid re-scraping unchanged prior-day data every run,
and (2) survive an outage. Backend doc §6 Critic finding: "Scraping sources
have no outage fallback — Recommended: stale-cache fallback with recorded
staleness, not hard failure." `fetch_with_disk_cache` implements exactly
that — a failed live fetch falls back to the last good cache and says so via
`CachedFrame.is_stale`, rather than either crashing the day's pipeline or
silently serving old data as if it were fresh.

CSV, not parquet: pyarrow isn't a declared project dependency (pyproject.toml
lists numpy/pandas/scipy/sklearn/httpx only) and these frames are small
per-season/per-day tables, so the format tradeoff doesn't matter here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

_META_SUFFIX = ".fetched_at"


class IngestSourceError(RuntimeError):
    """A live fetch failed and no usable cache existed to fall back to."""


@dataclass(frozen=True, slots=True)
class CachedFrame:
    frame: pd.DataFrame
    fetched_at_utc: datetime
    is_stale: bool
    """True if this is a fallback from a previous run, not a fresh fetch —
    callers (features/) should treat a stale frame as lower-confidence input,
    never as if `captured_at_utc` were `now`."""


def fetch_with_disk_cache(
    cache_path: Path,
    fetch: Callable[[], pd.DataFrame],
    *,
    now: datetime | None = None,
    max_age: timedelta | None = None,
) -> CachedFrame:
    """Try a fresh fetch; on any exception, fall back to the on-disk cache.

    `max_age`, when given, skips the network call entirely if the existing
    cache is younger than it — this is the "prior-day batch, disk-cached"
    half of the contract (backend doc §2.1): a source that's already been
    pulled once today doesn't need re-scraping just because a second job
    (e.g. both Pass A and Pass B, doc §2.4) reads the same feature. Leave it
    `None` to always attempt a fresh fetch and only fall back on failure.

    Raises `IngestSourceError` only when both the live fetch fails/is skipped
    AND no cache exists yet (e.g. first-ever run during an outage) — there is
    nothing safe to return in that case.
    """
    now = now or datetime.now(UTC)
    if max_age is not None:
        cached = _read(cache_path)
        if cached is not None and (now - cached[1]) <= max_age:
            return CachedFrame(frame=cached[0], fetched_at_utc=cached[1], is_stale=False)
    try:
        frame = fetch()
        _write(cache_path, frame, now)
        return CachedFrame(frame=frame, fetched_at_utc=now, is_stale=False)
    except Exception as exc:
        cached = _read(cache_path)
        if cached is None:
            raise IngestSourceError(
                f"live fetch failed and no cache at {cache_path}: {exc}"
            ) from exc
        frame, fetched_at = cached
        return CachedFrame(frame=frame, fetched_at_utc=fetched_at, is_stale=True)


def _write(cache_path: Path, frame: pd.DataFrame, at: datetime) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(cache_path, index=False)
    _meta_path(cache_path).write_text(at.isoformat(), encoding="utf-8")


def _read(cache_path: Path) -> tuple[pd.DataFrame, datetime] | None:
    if not cache_path.exists():
        return None
    frame = pd.read_csv(cache_path)
    meta_path = _meta_path(cache_path)
    fetched_at = (
        datetime.fromisoformat(meta_path.read_text(encoding="utf-8"))
        if meta_path.exists()
        else datetime.fromtimestamp(cache_path.stat().st_mtime, tz=UTC)
    )
    return frame, fetched_at


def _meta_path(cache_path: Path) -> Path:
    return cache_path.with_suffix(cache_path.suffix + _META_SUFFIX)
