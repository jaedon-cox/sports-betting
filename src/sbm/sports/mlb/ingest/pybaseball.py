"""FanGraphs + season-level Statcast aggregates: SIERA, xFIP, wRC+, xwOBA,
OAA (backend doc §2.1: "1x/day, prior-day batch, disk-cached").

Pitch-level CSW%/Stuff+ for low-sample/newly-promoted arms (model doc §3.1,
where a season aggregate lags) is `savant.py`'s job, not this module's.

**Build-time environment findings (message sent to `main`):**
- FanGraphs-backed calls (`pitching_stats`, `batting_stats`) returned HTTP 403
  from this dev sandbox. Baseball-Savant-direct calls (`statcast_*`) did not.
  Unconfirmed whether this is sandbox-IP-specific or durable — every fetcher
  here still goes through `cache.fetch_with_disk_cache`, so a blocked pull
  degrades to a stale cache rather than killing the day's run.
- pybaseball has **no numeric park-factor fetcher at all** — `park_codes()`
  only returns Retrosheet park IDs, and it is currently broken upstream (a
  `data.columns = parkcode_columns` fixed-width assignment against a
  Retrosheet CSV whose column count no longer matches, confirmed via source
  inspection, not just a bad response). Numeric run/HR park factors are not
  obtainable from this source at all. The structural park facts that *are*
  covered come from `statsapi/venue.py` (MLB's own `azimuthAngle`/`fieldInfo`),
  not from a hardcoded table; the numeric run/HR factor gap is flagged to
  `main` and leaves `park_run_factor` mostly null in v1 (`features/park.py`).

Every default fetch lazily imports `pybaseball` so this module is importable
without the optional `mlb` extra installed, and tests inject a fake `fetch`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd

from sbm.sports.mlb.ingest.cache import CachedFrame, fetch_with_disk_cache

ColumnMap = dict[str, tuple[str, ...]]

PITCHING_COLUMNS: ColumnMap = {
    "player_id": ("IDfg", "playerid", "player_id"),
    "name": ("Name", "name"),
    "team": ("Team", "team"),
    "siera": ("SIERA", "siera"),
    "xfip": ("xFIP", "xfip"),
    "k_pct": ("K%", "k_percent"),
    "bb_pct": ("BB%", "bb_percent"),
    "csw_pct": ("CSW%", "csw_percent"),
}

BATTING_COLUMNS: ColumnMap = {
    "player_id": ("IDfg", "playerid", "player_id"),
    "name": ("Name", "name"),
    "team": ("Team", "team"),
    "wrc_plus": ("wRC+", "wrc_plus"),
}

XWOBA_COLUMNS: ColumnMap = {
    "player_id": ("player_id",),
    "name": ("last_name, first_name", "name"),
    "xwoba": ("est_woba",),
    "woba": ("woba",),
}

OAA_COLUMNS: ColumnMap = {
    "player_id": ("player_id",),
    "name": ("last_name, first_name", "name"),
    "team": ("display_team_name", "team_name"),
    "oaa": ("outs_above_average",),
}

Fetch = Callable[[], pd.DataFrame]


def fetch_pitching_stats(season: int, *, cache_dir: Path, fetch: Fetch | None = None) -> CachedFrame:
    """Season-to-date SIERA/xFIP/K%/BB%/CSW% for qualified pitchers."""
    fetch = fetch or _lazy(lambda: __import__("pybaseball").pitching_stats(season, season, qual=0))
    return fetch_with_disk_cache(
        cache_dir / f"pitching_stats_{season}.csv",
        _normalizing(fetch, PITCHING_COLUMNS),
    )


def fetch_batting_stats(season: int, *, cache_dir: Path, fetch: Fetch | None = None) -> CachedFrame:
    """Season-to-date wRC+ for qualified batters."""
    fetch = fetch or _lazy(lambda: __import__("pybaseball").batting_stats(season, season, qual=0))
    return fetch_with_disk_cache(
        cache_dir / f"batting_stats_{season}.csv",
        _normalizing(fetch, BATTING_COLUMNS),
    )


def fetch_batter_xwoba(season: int, *, cache_dir: Path, fetch: Fetch | None = None) -> CachedFrame:
    """Statcast expected-wOBA — the "deserved vs actual" mispricing input
    (model doc §3.4) layered on top of wRC+."""
    fetch = fetch or _lazy(
        lambda: __import__("pybaseball").statcast_batter_expected_stats(season, minPA=1)
    )
    return fetch_with_disk_cache(
        cache_dir / f"batter_xwoba_{season}.csv",
        _normalizing(fetch, XWOBA_COLUMNS),
    )


def fetch_oaa(season: int, *, cache_dir: Path, fetch: Fetch | None = None) -> CachedFrame:
    """Statcast Outs Above Average — team defense input (model doc §3.9,
    §10.3), shrunk heavily behind a CLV test per the doc's CONDITIONAL verdict."""
    fetch = fetch or _lazy(lambda: __import__("pybaseball").statcast_outs_above_average(season, "all"))
    return fetch_with_disk_cache(
        cache_dir / f"oaa_{season}.csv",
        _normalizing(fetch, OAA_COLUMNS),
    )


def _lazy(build: Fetch) -> Fetch:
    """Defers both the `pybaseball` import and the network call until the
    disk cache actually needs a fresh fetch."""
    return build


def _normalizing(fetch: Fetch, column_map: ColumnMap) -> Fetch:
    def wrapped() -> pd.DataFrame:
        return _normalize(fetch(), column_map)

    return wrapped


def _normalize(frame: pd.DataFrame, column_map: ColumnMap) -> pd.DataFrame:
    """Map source column names to our canonical names; a candidate missing
    upstream (shape drift) degrades that column to NA instead of raising —
    defensive handling per the ingest brief, since this is an unofficial,
    scraping-based source with no SLA."""
    out = pd.DataFrame(index=frame.index)
    for canonical, candidates in column_map.items():
        match = next((c for c in candidates if c in frame.columns), None)
        out[canonical] = frame[match] if match is not None else pd.NA
    return out
