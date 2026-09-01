"""Every Postgres function the pipeline calls, and the row shapes they return.

`store/` is write-only by design ("Reads for the frontend go straight to
Postgres ... there is no REST read layer in this package") and
`PostgrestClient` exposes no filtered select — only insert/upsert/patch/rpc. So
every read here is a Postgres function called over `rpc()`, following
`fn_odds_budget_month_total`'s precedent: a named function per read the
pipeline actually needs, rather than a general-purpose query builder that would
let any job invent its own point-in-time semantics.

`REFRESH MATERIALIZED VIEW` is not expressible over PostgREST at all, which is
why `fn_refresh_rollups` exists rather than a statement per view.

The functions are `db`'s (migrations 011, 012, 014, and 015 for the backtest
loader in `job_g_backtest.py`); every one of them is `REVOKE`d from anon and
authenticated and granted to `service_role` only, which is the key these jobs
run under. This module is the only place their names and column shapes appear,
so a rename upstream changes exactly one file.

Cross-layer id rule: `game_id` here is `games.id`, the Postgres surrogate.
`external_game_id` is the MLB gamePk and is the only id that may cross into
`sports/*/features/` (CLAUDE.md, `contracts/feature.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sbm.store.client import PostgrestClient


@dataclass(frozen=True, slots=True)
class LineQuote:
    """One `line_snapshots` row as a job consumes it for pricing."""

    game_id: int
    market: str
    side: str
    line: float | None
    price_american: int
    implied_prob_devigged: float | None
    """Both this and `devig_method` are nullable in `line_snapshots`, and 004
    constrains them to be null or non-null together. A null pair means the row
    was written without a de-vig; `pricing._fair_probs` computes one rather
    than treating the quote as unusable."""
    devig_method: str | None
    captured_at_utc: datetime
    is_closing: bool


@dataclass(frozen=True, slots=True)
class SettledPick:
    """A settled pick, as the calibration rollup reads it."""

    market: str
    model_prob: float
    outcome: str


@dataclass(frozen=True, slots=True)
class UnsettledPick:
    """A pick whose game has finished but which has no `pick_settlements` row.

    `closing_prob`/`closing_line` come from the `is_closing` snapshot for the
    same (game, market, side, book) and are None when no close was captured —
    a postponed game or a missed sweep. That is a null row for Job F, never a
    raise (see `job_f_settlement/outcomes.py`).
    """

    pick_id: int
    game_id: int
    market: str
    side: str
    line: float | None
    bet_prob: float | None
    """`picks.market_fair_prob` — the de-vigged price the pick was taken at."""
    model_prob: float
    game_status: str
    home_score: int | None
    away_score: int | None
    game_date: date
    closing_prob: float | None
    closing_line: float | None


def latest_lines(
    client: PostgrestClient, *, sport: str, game_date: date, as_of: datetime
) -> list[LineQuote]:
    """Latest snapshot per (game, market, side) at or before `as_of`.

    The as-of filter is the point (backend doc §3.2: `WHERE captured_at_utc <=
    ... ORDER BY captured_at_utc DESC LIMIT 1`). A pick priced against a
    snapshot taken after it was locked would make its own CLV meaningless.
    """
    rows = client.rpc(
        "fn_latest_lines",
        {"p_sport": sport, "p_game_date": game_date.isoformat(), "p_as_of": as_of.isoformat()},
    )
    return [_line_quote(row) for row in rows or []]


def unsettled_picks(
    client: PostgrestClient, *, sport: str, before: datetime
) -> list[UnsettledPick]:
    """Picks on finished/terminal games that Job F has not settled yet.

    Idempotency comes from the absence of a `pick_settlements` row rather than
    from a date filter, so a rerun after a partial night settles only what is
    still missing — `pick_settlements` is insert-once and a second insert would
    be a primary-key violation, not an overwrite.
    """
    rows = client.rpc(
        "fn_unsettled_picks", {"p_sport": sport, "p_before": before.isoformat()}
    )
    return [_unsettled_pick(row) for row in rows or []]


def settled_picks_for_date(
    client: PostgrestClient, *, sport: str, rollup_date: date
) -> list[SettledPick]:
    """Every settled pick on one slate date — the complete set, not a delta.

    `calibration_buckets` is upserted per (rollup_date, bucket), so a rerun that
    settled only the stragglers must still recompute each bucket from the whole
    day or it would overwrite a full bucket with a partial one. Complete-set-in,
    complete-row-out is what makes that upsert idempotent (backend doc §3.3).
    """
    rows = client.rpc(
        "fn_settled_picks_for_date",
        {"p_sport": sport, "p_rollup_date": rollup_date.isoformat()},
    )
    return [
        SettledPick(
            market=str(row["market"]),
            model_prob=float(row["model_prob"]),
            outcome=str(row["outcome"]),
        )
        for row in rows or []
    ]


def record_results(client: PostgrestClient, results: list[dict[str, Any]]) -> int:
    """Insert final scores, skipping games already recorded; returns rows added.

    `results` is insert-once and carries a reject-mutation trigger, so neither
    `insert` (unique violation on a rerun) nor `upsert` (PostgREST's
    merge-duplicates issues ON CONFLICT DO UPDATE, which the trigger rejects)
    is usable. `fn_record_results` does `ON CONFLICT (game_id) DO NOTHING`,
    which fires no UPDATE and so leaves the append-only guarantee intact.
    """
    if not results:
        return 0
    return int(client.rpc("fn_record_results", {"p_results": results}))


def refresh_rollups(client: PostgrestClient) -> None:
    """Plain (NOT concurrent) `REFRESH MATERIALIZED VIEW` on all four rollups.

    `record_summary` first, then `mv_clv_trend` and `mv_roi_curve`, which are
    windows over it and would otherwise publish a cumulative curve disagreeing
    with its own daily rows, then `record_breakdown`. Order is why this is one
    function rather than four calls a job could sequence wrong.

    **Not `CONCURRENTLY`, and no arrangement of PL/pgSQL makes it so** —
    `REFRESH ... CONCURRENTLY` cannot run inside a transaction block and a
    plpgsql body always is one, so it fails with "cannot be executed from a
    function" (db/migrations/011). §3.3's note that concurrent refresh needs a
    unique index on the matview still holds for a manual `psql` refresh; it does
    not describe this path. The cost is an ACCESS EXCLUSIVE lock for the length
    of the call, which is milliseconds against a few thousand rollup rows in a
    nightly job.

    `calibration_buckets` is NOT in here: it is a physical table and Job F
    upserts it, precisely so a new bucketing method cannot silently rewrite past
    numbers (backend doc §3.3).
    """
    client.rpc("fn_refresh_rollups", {})


def _line_quote(row: dict[str, Any]) -> LineQuote:
    return LineQuote(
        game_id=int(row["game_id"]),
        market=str(row["market"]),
        side=str(row["side"]),
        line=_opt_float(row.get("line")),
        price_american=int(row["price_american"]),
        implied_prob_devigged=_opt_float(row.get("implied_prob_devigged")),
        devig_method=None if row.get("devig_method") is None else str(row["devig_method"]),
        captured_at_utc=datetime.fromisoformat(str(row["captured_at_utc"])),
        is_closing=bool(row["is_closing"]),
    )


def _unsettled_pick(row: dict[str, Any]) -> UnsettledPick:
    return UnsettledPick(
        pick_id=int(row["pick_id"]),
        game_id=int(row["game_id"]),
        market=str(row["market"]),
        side=str(row["side"]),
        line=_opt_float(row.get("line")),
        bet_prob=_opt_float(row.get("bet_prob")),
        model_prob=float(row["model_prob"]),
        game_status=str(row["game_status"]),
        home_score=_opt_int(row.get("home_score")),
        away_score=_opt_int(row.get("away_score")),
        game_date=date.fromisoformat(str(row["game_date"])),
        closing_prob=_opt_float(row.get("closing_prob")),
        closing_line=_opt_float(row.get("closing_line")),
    )


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)
