"""The atomic-publish writer `model` calls once per (run_date, pass_type).

Wraps db/migrations/007_atomic_publish.sql's fn_publish_run RPC — a
single Postgres function call is one implicit transaction, so inserting
every pick in the slate and flipping model_runs from 'running' to
'success' either all land or none do (§2.4). No business logic: this
module only shapes the payload and calls the RPC.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from sbm.store.client import PostgrestClient


@dataclass(frozen=True, slots=True)
class PickRow:
    """One row `model` produces per (game, market) for a run's slate.

    Matches picks columns exactly, minus id/model_run_id/created_at,
    which the server assigns. player_id/stat_type are None for every
    current MLB team-market pick — non-None only for a player prop;
    fn_validate_pick (db/migrations/003_picks.sql) enforces that split
    server-side, so a mismatch here surfaces as a publish_run() error
    rather than a silently wrong row.
    """

    game_id: int
    game_date: date
    market: str
    side: str
    raw_model_prob: float
    model_prob: float
    recommended: bool
    kelly_stake_fraction: float
    pick_locked_at: datetime
    line: float | None = None
    player_id: str | None = None
    stat_type: str | None = None
    market_fair_prob: float | None = None
    devig_method: str | None = None
    market_odds_american: int | None = None
    book: str = "pinnacle"
    edge_pct: float | None = None

    def __post_init__(self) -> None:
        """Mirror 003's CHECK ((market_fair_prob IS NULL) = (devig_method IS
        NULL)) locally, the way LineSnapshotRow mirrors 004's identical
        pairing. Both columns record which de-vig method actually produced
        the number on THIS row: picks is append-only, so a backtest has to
        be able to prove the provenance even after markets.devig_method
        changes. Failing here names the field; the publish RPC would fail
        as a constraint violation that rolls back the entire slate.
        """
        if (self.market_fair_prob is None) != (self.devig_method is None):
            raise ValueError(
                "market_fair_prob and devig_method must both be set or both be None "
                f"(got {self.market_fair_prob!r}, {self.devig_method!r})"
            )

    def to_json(self) -> dict[str, Any]:
        row = asdict(self)
        row["game_date"] = self.game_date.isoformat()
        row["pick_locked_at"] = self.pick_locked_at.isoformat()
        return row


def publish_run(
    client: PostgrestClient,
    *,
    model_version_id: int,
    sport: str,
    run_date: date,
    pass_type: str,
    picks: list[PickRow],
    github_run_id: str | None = None,
) -> int:
    """Atomically publish a full day's slate and return the model_run id.

    Idempotent (§2.4): a retry against an already-`status='success'`
    (model_version, run_date, pass_type) is a no-op that returns the
    existing model_run id rather than raising or duplicating rows.
    """
    result = client.rpc(
        "fn_publish_run",
        {
            "p_model_version_id": model_version_id,
            "p_sport": sport,
            "p_run_date": run_date.isoformat(),
            "p_pass_type": pass_type,
            "p_github_run_id": github_run_id,
            "p_picks": [pick.to_json() for pick in picks],
        },
    )
    return int(result)
