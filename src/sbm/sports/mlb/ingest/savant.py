"""Pitch-level Statcast data for CSW%/Stuff+-adjacent features.

Model doc §3.1: Stuff+/pitch-level data's "strongest edge [is for]
newly-promoted / low-sample arms where rate stats are noisy and the market is
slow" — a season aggregate from `pybaseball.py` lags exactly there, because a
brand-new starter doesn't have a season yet. This module fetches the raw
pitches so `features/pitcher.py` can compute CSW% and velo/movement trends
over any window, including a pitcher's first handful of outings.

CSW% = (called strikes + whiffs) / total pitches (PitcherList's standard
definition). "Whiff" is `swinging_strike` + `swinging_strike_blocked`;
`foul_tip` is deliberately excluded — it's contact, not a miss.

Full "Stuff+" (a trained model over release/movement/spin characteristics) is
out of scope for ingest — this module only fetches the raw pitch
characteristics (`release_speed`, `release_spin_rate`, `pfx_x`, `pfx_z`,
`release_extension`) that such a feature needs; it doesn't train or apply
the model itself.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pandas as pd

from sbm.sports.mlb.ingest.cache import CachedFrame, fetch_with_disk_cache

PITCH_COLUMNS = (
    "pitcher",
    "player_name",
    "game_date",
    "pitch_type",
    "release_speed",
    "release_spin_rate",
    "pfx_x",
    "pfx_z",
    "release_extension",
    "description",
    "zone",
)

WHIFF_DESCRIPTIONS = frozenset({"swinging_strike", "swinging_strike_blocked"})
CALLED_STRIKE_DESCRIPTION = "called_strike"

Fetch = Callable[[], pd.DataFrame]


def fetch_pitch_level(
    start_date: date,
    end_date: date,
    *,
    cache_dir: Path,
    fetch: Fetch | None = None,
) -> CachedFrame:
    """Every pitch thrown in `[start_date, end_date]`, trimmed to the columns
    CSW%/Stuff+-style features need. Nightly batch, prior-day range (backend
    doc §2.1)."""
    fetch = fetch or _default_fetch(start_date, end_date)
    cache_path = cache_dir / f"pitch_level_{start_date.isoformat()}_{end_date.isoformat()}.csv"
    return fetch_with_disk_cache(cache_path, _trimming(fetch))


def compute_csw_pct(pitch_level: pd.DataFrame) -> pd.DataFrame:
    """Per-pitcher CSW% and pitch count over whatever window `pitch_level`
    covers — a pure aggregation, no I/O, so it runs over any trailing window
    a feature builder chooses. EWMA half-lives (model doc §10.1) are the
    caller's concern, not this function's."""
    if pitch_level.empty or "pitcher" not in pitch_level.columns:
        return pd.DataFrame(columns=["pitcher", "n_pitches", "csw_pct"])
    is_csw = pitch_level["description"].isin(WHIFF_DESCRIPTIONS | {CALLED_STRIKE_DESCRIPTION})
    working = pitch_level.assign(_is_csw=is_csw)
    return working.groupby("pitcher")["_is_csw"].agg(n_pitches="count", csw_pct="mean").reset_index()


def _default_fetch(start_date: date, end_date: date) -> Fetch:
    def fetch() -> pd.DataFrame:
        import pybaseball as pb  # lazy: optional `mlb` extra, and slow to import

        return pb.statcast(start_date.isoformat(), end_date.isoformat())

    return fetch


def _trimming(fetch: Fetch) -> Fetch:
    def wrapped() -> pd.DataFrame:
        raw = fetch()
        cols = [c for c in PITCH_COLUMNS if c in raw.columns]
        return raw[cols].copy()

    return wrapped
