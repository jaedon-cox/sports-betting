"""Job I — nightly Statcast pull into the per-game feature store.

The job that makes Jobs C and D possible. Everything the model reads about
pitchers and hitters comes from `pitcher_game_stats` / `team_batting_game_stats`
(db/migrations/017), and this is the only thing that writes them.

**Runs after Job F, not before.** F settles the previous slate at ~4am ET; this
runs at ~5am and covers the same games. Ordering matters only because both
re-pull a window and there is no reason to contend for the same StatsAPI
budget, not because either depends on the other's rows.

**Re-covers a trailing window rather than only yesterday.** Statcast revises a
game for a day or two after it is played — an event reclassified, an xwOBA
recomputed — so a strictly incremental pull would freeze the first version.
`LOOKBACK_DAYS` is the width of that window, and the writer upserts, so
re-covering is free.

**No Odds API cost and no `raw_snapshots` archive.** Statcast is bulk history
with no leakage risk and §3.6 explicitly excludes it from the append-only blob
store; the disk cache in `ingest/cache.py` is its durability story instead.

**Backfill is the same code path**, driven by `SBM_BACKFILL_FROM` /
`SBM_BACKFILL_TO`. That is deliberate: a backfill that ran different code from
the nightly job would produce a subtly different history to backtest against,
which is the failure this repo avoids everywhere else by refusing to fork live
and backtest paths (CLAUDE.md rule 4).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path

from sbm.jobs.context import JobContext
from sbm.store.game_stats import (
    PitcherGameRow,
    TeamBattingGameRow,
    upsert_pitcher_game_stats,
    upsert_team_batting_game_stats,
)

JOB_NAME = "job_i_statcast"

LOOKBACK_DAYS = 3
"""Trailing window re-covered every night. Two would cover Statcast's revision
lag; three costs one extra day of a cached bulk pull and tolerates a missed
run without needing a manual backfill."""

CACHE_DIR = Path(os.environ.get("SBM_CACHE_DIR", ".cache/statcast"))
"""Disk cache for the raw pull. Ephemeral on an Actions runner — the cache is a
courtesy for local and backfill runs, not a durability guarantee; Postgres is
where the aggregates actually live."""


def run(ctx: JobContext) -> str:
    start, end = _window(ctx)
    pitchers, batting, stale = _aggregate(start, end)
    n_pitchers = upsert_pitcher_game_stats(ctx.client, pitchers)
    n_batting = upsert_team_batting_game_stats(ctx.client, batting)
    note = " (STALE CACHE — live fetch failed)" if stale else ""
    return (
        f"{start}..{end}: {n_pitchers} pitcher-game rows, "
        f"{n_batting} team-batting rows{note}"
    )


def _window(ctx: JobContext) -> tuple[date, date]:
    """The date range to cover — the trailing window, or an explicit backfill.

    Both bounds must be set for a backfill; one alone is a typo, and silently
    treating it as "since the beginning of time" would pull two decades of
    pitch-level data on a mistyped dispatch input.
    """
    since, until = os.environ.get("SBM_BACKFILL_FROM"), os.environ.get("SBM_BACKFILL_TO")
    if since and until:
        return date.fromisoformat(since), date.fromisoformat(until)
    if since or until:
        raise ValueError(
            "SBM_BACKFILL_FROM and SBM_BACKFILL_TO must both be set or both unset "
            f"(got from={since!r}, to={until!r})"
        )
    end = ctx.slate_date - timedelta(days=1)
    return end - timedelta(days=LOOKBACK_DAYS - 1), end


def _aggregate(
    start: date, end: date
) -> tuple[list[PitcherGameRow], list[TeamBattingGameRow], bool]:
    """Pull the window and turn it into rows. Third value is "came from cache".

    **Goes to `cache.fetch_with_disk_cache` directly rather than through
    `savant.fetch_pitch_level`.** That helper wraps every fetch — including an
    injected one — in `_trimming`, which narrows the frame to its
    CSW%/Stuff+ column set and drops `events`, `bb_type`, `p_throws`, `stand`,
    `game_pk` and both team fields. Those are precisely what the per-game
    aggregation is built on, so its extension point cannot be used here; the
    cache primitive underneath it can, and gives the same
    fall-back-to-disk-on-failure behaviour.

    The pandas boundary lives here, deliberately. `store/` must stay free of the
    scientific stack or Jobs B and H start installing it on every one of their
    ~430 monthly invocations (`tests/unit/jobs/test_dependency_profile.py`), so
    the frame becomes dataclasses before it crosses into the writer.
    """
    from sbm.sports.mlb.ingest.cache import fetch_with_disk_cache
    from sbm.sports.mlb.ingest.statcast_games import (
        aggregate_pitcher_games,
        aggregate_team_batting_games,
    )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"pitch_level_{start.isoformat()}_{end.isoformat()}.csv"
    cached = fetch_with_disk_cache(cache_path, _wide_fetch(start, end))
    frame = cached.frame
    return (
        [_pitcher_row(r) for r in aggregate_pitcher_games(frame).to_dict("records")],
        [_batting_row(r) for r in aggregate_team_batting_games(frame).to_dict("records")],
        cached.is_stale,
    )


def _wide_fetch(start: date, end: date):
    """The untrimmed Statcast pull — every column, for the reason above."""

    def fetch():
        import pybaseball as pb  # lazy: the optional `mlb` extra

        return pb.statcast(start.isoformat(), end.isoformat())

    return fetch


def _pitcher_row(row: dict) -> PitcherGameRow:
    return PitcherGameRow(
        player_id=str(row["pitcher"]),
        game_pk=str(row["game_pk"]),
        game_date=_as_date(row["game_date"]),
        pitching_team=str(row["pitching_team"]),
        throws=_hand(row.get("p_throws")),
        is_start=bool(row["is_start"]),
        pitches=int(row["pitches"]),
        csw=int(row["csw"]),
        batters_faced=int(row["batters_faced"]),
        outs=int(row["outs"]),
        strikeouts=int(row["strikeouts"]),
        walks=int(row["walks"]),
        hit_by_pitch=int(row["hit_by_pitch"]),
        home_runs=int(row["home_runs"]),
        ground_balls=int(row["ground_balls"]),
        fly_balls=int(row["fly_balls"]),
        line_drives=int(row["line_drives"]),
        popups=int(row["popups"]),
    )


def _batting_row(row: dict) -> TeamBattingGameRow:
    return TeamBattingGameRow(
        game_pk=str(row["game_pk"]),
        game_date=_as_date(row["game_date"]),
        batting_team=str(row["batting_team"]),
        opp_hand=str(row["opp_hand"]),
        plate_appearances=int(row["plate_appearances"]),
        xwoba_sum=float(row["xwoba_sum"]),
    )


def _hand(value: object) -> str | None:
    """'L'/'R', or None for the handful of rows where Statcast omits it —
    `PitcherGameRow` rejects anything else, mirroring 017's CHECK."""
    text = None if value is None else str(value).strip().upper()
    return text if text in ("L", "R") else None


def _as_date(value: object) -> date:
    """Statcast's `game_date` arrives as a pandas Timestamp or an ISO string
    depending on how the frame was built; both become a plain `date` here.

    The `datetime` branch has to come first. `pd.Timestamp` subclasses
    `datetime`, which subclasses `date`, so a bare `isinstance(value, date)`
    matches a Timestamp and passes it through untouched — and
    `store.game_stats._row` then serialises it as "2026-08-30T00:00:00" into a
    DATE column. Postgres would accept that and the row would look right,
    which is exactly why it is worth being explicit about.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
