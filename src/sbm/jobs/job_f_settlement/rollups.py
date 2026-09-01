"""The Model Record page's two write paths: calibration buckets, then matviews.

Both are Job F's, and skipping either leaves the page empty by construction —
nothing aggregates raw `picks` at request time (backend doc §3.3).

**`calibration_buckets` is UPSERTed, never REFRESHed.** It is a physical table
precisely because a REFRESH would recompute all history under any new bucketing
method and silently change past numbers; the explicit
`ON CONFLICT (rollup_date, sport, market, predicted_bucket, method_version)`
means a dashboard pinned to an old `method_version` stays numerically stable
(§3.3, and the header comment on `db/views/calibration_buckets.sql`).

**The bucketing runs in Python, not SQL, and `METHOD_VERSION` is why.** §3.3's
whole point is that the method is a versioned artifact — so it belongs where it
can be versioned with the code that produced it, next to the string that names
it. `fn_settled_picks_for_date` returns the *complete* settled set for a date
rather than the night's delta, which is what makes recomputing each bucket from
scratch (and therefore the upsert) idempotent.

**Pushes and voids are excluded.** A push is not a binary outcome, and scoring
it as a loss would drag every bucket's empirical rate below its true value —
the same reason `core.backtest.calibrate` drops them before fitting.

The matviews are refreshed after by `fn_refresh_rollups`, which owns the
dependency order — `record_summary` first, since `mv_clv_trend` and
`mv_roi_curve` are windows over it and would otherwise publish a cumulative
curve disagreeing with its own daily rows (db/migrations/011).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sbm.jobs.rpc import SettledPick, refresh_rollups, settled_picks_for_date
from sbm.store.client import PostgrestClient

METHOD_VERSION = "v1-decile"
"""v1 (§3.3): blended across markets, 10 equal-width deciles of `model_prob`,
win/loss only. A change to any of those three is a new version string, never an
edit to this one — that is what keeps a pinned dashboard stable."""

BLENDED = "blended"
"""§3.3's v1 grain. `record_summary` uses the same non-NULL sentinel, because
ON CONFLICT needs a real value to match on (two NULLs never conflict)."""

N_BUCKETS = 10
TABLE = "calibration_buckets"
ON_CONFLICT = "rollup_date,sport,market,predicted_bucket,method_version"

_SCORED_OUTCOMES = frozenset({"win", "loss"})


def upsert_calibration_buckets(
    client: PostgrestClient, *, sport: str, rollup_date: date
) -> int:
    """Recompute and upsert one date's deciles. Returns the bucket count."""
    settled = settled_picks_for_date(client, sport=sport, rollup_date=rollup_date)
    rows = bucket_rows(settled, sport=sport, rollup_date=rollup_date)
    client.upsert(TABLE, rows, on_conflict=ON_CONFLICT)
    return len(rows)


def bucket_rows(
    settled: list[SettledPick], *, sport: str, rollup_date: date
) -> list[dict[str, Any]]:
    """Deciles of `model_prob` with their empirical win rate, blended."""
    buckets: dict[int, list[SettledPick]] = {}
    for pick in settled:
        if pick.outcome not in _SCORED_OUTCOMES:
            continue
        buckets.setdefault(decile(pick.model_prob), []).append(pick)
    return [
        {
            "rollup_date": rollup_date.isoformat(),
            "sport": sport,
            "market": BLENDED,
            "predicted_bucket": bucket,
            "method_version": METHOD_VERSION,
            "n": len(picks),
            "avg_predicted_prob": sum(p.model_prob for p in picks) / len(picks),
            "actual_win_rate": sum(1 for p in picks if p.outcome == "win") / len(picks),
        }
        for bucket, picks in sorted(buckets.items())
    ]


def decile(prob: float) -> int:
    """1..10, matching Postgres `width_bucket(prob, 0, 1, 10)`.

    A probability of exactly 1.0 lands in bucket 10 rather than an 11th, which
    is the clamp `width_bucket` would otherwise need and the reason the schema's
    CHECK is `BETWEEN 1 AND 10`.
    """
    return min(N_BUCKETS, max(1, int(prob * N_BUCKETS) + 1))


def refresh_matviews(client: PostgrestClient) -> None:
    """Every rollup matview, in the order `fn_refresh_rollups` defines."""
    refresh_rollups(client)
