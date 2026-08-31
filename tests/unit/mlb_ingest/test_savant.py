"""Offline tests — every fetch is injected, no real pybaseball/network call."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from sbm.sports.mlb.ingest.savant import compute_csw_pct, fetch_pitch_level

RAW_PITCHES = pd.DataFrame(
    {
        "pitcher": [1, 1, 1, 1, 2, 2],
        "player_name": ["A", "A", "A", "A", "B", "B"],
        "game_date": ["2026-06-01"] * 6,
        "pitch_type": ["FF"] * 6,
        "release_speed": [95.0] * 6,
        "release_spin_rate": [2200] * 6,
        "description": [
            "called_strike",
            "swinging_strike",
            "ball",
            "foul",
            "ball",
            "hit_into_play",
        ],
        "unexpected_upstream_column": ["x"] * 6,  # simulates shape drift
    }
)


def test_fetch_pitch_level_trims_to_known_columns_and_drops_unknown_ones(tmp_path: Path) -> None:
    result = fetch_pitch_level(date(2026, 6, 1), date(2026, 6, 1), cache_dir=tmp_path, fetch=lambda: RAW_PITCHES)
    assert "unexpected_upstream_column" not in result.frame.columns
    assert "pitcher" in result.frame.columns


def test_compute_csw_pct_matches_the_standard_definition() -> None:
    csw = compute_csw_pct(RAW_PITCHES).set_index("pitcher")
    # Pitcher 1: 4 pitches, called_strike + swinging_strike = 2 CSW -> 0.5
    assert csw.loc[1, "n_pitches"] == 4
    assert csw.loc[1, "csw_pct"] == 0.5
    # Pitcher 2: 2 pitches, 0 CSW (ball, hit_into_play) -> 0.0
    assert csw.loc[2, "n_pitches"] == 2
    assert csw.loc[2, "csw_pct"] == 0.0


def test_compute_csw_pct_excludes_foul_tip_from_whiffs() -> None:
    pitches = pd.DataFrame({"pitcher": [1, 1], "description": ["foul_tip", "ball"]})
    csw = compute_csw_pct(pitches).set_index("pitcher")
    assert csw.loc[1, "csw_pct"] == 0.0


def test_compute_csw_pct_on_empty_frame_returns_empty_result() -> None:
    result = compute_csw_pct(pd.DataFrame(columns=["pitcher", "description"]))
    assert result.empty
    assert list(result.columns) == ["pitcher", "n_pitches", "csw_pct"]
