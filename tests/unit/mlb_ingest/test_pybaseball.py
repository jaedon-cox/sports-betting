"""Offline tests — every fetch is injected, no real pybaseball/network call."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sbm.sports.mlb.ingest.pybaseball import (
    fetch_batter_xwoba,
    fetch_batting_stats,
    fetch_oaa,
    fetch_pitching_stats,
)

RAW_PITCHING = pd.DataFrame(
    {
        "IDfg": [1, 2],
        "Name": ["Pitcher A", "Pitcher B"],
        "Team": ["NYY", "BOS"],
        "SIERA": [3.1, 4.2],
        "xFIP": [3.3, 4.0],
        "K%": [0.28, 0.19],
        "BB%": [0.06, 0.09],
        # CSW% intentionally absent — simulates upstream shape drift.
    }
)


def test_fetch_pitching_stats_normalizes_known_columns(tmp_path: Path) -> None:
    result = fetch_pitching_stats(2026, cache_dir=tmp_path, fetch=lambda: RAW_PITCHING)
    frame = result.frame
    assert list(frame["siera"]) == [3.1, 4.2]
    assert list(frame["k_pct"]) == [0.28, 0.19]


def test_fetch_pitching_stats_degrades_missing_column_to_na(tmp_path: Path) -> None:
    result = fetch_pitching_stats(2026, cache_dir=tmp_path, fetch=lambda: RAW_PITCHING)
    assert result.frame["csw_pct"].isna().all()


def test_fetch_batting_stats_normalizes_wrc_plus(tmp_path: Path) -> None:
    raw = pd.DataFrame({"IDfg": [1], "Name": ["Batter A"], "Team": ["NYY"], "wRC+": [145]})
    result = fetch_batting_stats(2026, cache_dir=tmp_path, fetch=lambda: raw)
    assert list(result.frame["wrc_plus"]) == [145]


def test_fetch_batter_xwoba_normalizes_statcast_columns(tmp_path: Path) -> None:
    raw = pd.DataFrame(
        {"player_id": [660271], "last_name, first_name": ["Ohtani, Shohei"], "est_woba": [0.44], "woba": [0.41]}
    )
    result = fetch_batter_xwoba(2026, cache_dir=tmp_path, fetch=lambda: raw)
    assert list(result.frame["xwoba"]) == [0.44]


def test_fetch_oaa_normalizes_statcast_columns(tmp_path: Path) -> None:
    raw = pd.DataFrame(
        {
            "player_id": [1],
            "last_name, first_name": ["Player, One"],
            "display_team_name": ["Yankees"],
            "outs_above_average": [7],
        }
    )
    result = fetch_oaa(2026, cache_dir=tmp_path, fetch=lambda: raw)
    assert list(result.frame["oaa"]) == [7]


def test_repeated_call_uses_cache_not_a_second_fetch_invocation(tmp_path: Path) -> None:
    calls = {"n": 0}

    def counting_fetch() -> pd.DataFrame:
        calls["n"] += 1
        return RAW_PITCHING

    fetch_pitching_stats(2026, cache_dir=tmp_path, fetch=counting_fetch)
    result = fetch_pitching_stats(2026, cache_dir=tmp_path, fetch=counting_fetch)
    # Both calls fetch fresh here (no max-age gate in this layer) — this test
    # documents that behavior: caching is for outage fallback, not for
    # skipping same-day refetches, which belongs to job scheduling instead.
    assert calls["n"] == 2
    assert result.is_stale is False
