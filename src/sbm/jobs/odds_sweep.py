"""One priced Odds API snapshot: charge -> fetch -> archive -> normalize -> insert.

Shared by Job A's daily open and Job E's closing sweeps, which differ only in
which games are flagged `is_closing`. Both spend 3 credits (3 markets x 1
region) and both cover the entire upcoming window in a single slate-wide call —
`fetch_odds` sends no date parameter, so a sweep aimed at the 7pm cluster also
captures a free non-closing snapshot of everything else on the board.

**The raw payload is archived here, at the job layer.** `fetch_odds` has no
`capture=` seam on purpose: adding one would make `sbm.odds.theoddsapi` import
`sbm.sports.mlb.ingest.archive` while `statsapi.teams` already imports
`sbm.odds.resolution`, i.e. a package cycle. It returns the untouched payload
instead, and this is the one place holding both those bytes and a DB client.

**Unresolvable games are routine.** Doubleheaders are deliberately not
disambiguated (charging a line to the wrong half of a twin bill is worse than
skipping it) and off-slate games arrive by construction, since the feed spans a
wider window than the one `officialDate` the resolver is built from. Only
`NOT_INGESTED` means something upstream is broken, which is why
`alerting_skips` keys on that reason specifically and never on "skipped > 0".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

from sbm.jobs.archive import archive_odds_payload
from sbm.jobs.slate_ingest import Slate
from sbm.odds.budget import OddsBudget
from sbm.odds.resolution import NOT_INGESTED, ResolvedExternalId
from sbm.odds.snapshot import NormalizedSnapshot, normalize_snapshot
from sbm.odds.snapshot.rows import LineSnapshotRow as NormalizedRow
from sbm.odds.theoddsapi import MARKETS, fetch_odds
from sbm.sports.mlb.ingest.statsapi import build_external_game_id_resolver
from sbm.store.client import PostgrestClient
from sbm.store.snapshots import LineSnapshotRow, insert_line_snapshots

CREDITS_PER_SWEEP = len(MARKETS)
"""3 markets x 1 region — The Odds API's `markets x regions` formula (§2.5)."""

NOT_INGESTED_ALERT_THRESHOLD = 0
"""How many `NOT_INGESTED` skips are tolerable before a sweep is a failure.

Zero, because every sweep runs after `slate_ingest.ingest_slate` has upserted
the day's games: a gamePk the odds feed knows and `games` does not means the
schedule join is broken, not that the feed ran ahead of us. The other three
reasons are never counted here — a doubleheader we refuse to disambiguate and
an off-slate game from the feed's wider window are both ordinary Tuesdays."""


class SlateIntegrityError(RuntimeError):
    """A sweep resolved fewer games than the slate says exist."""


@dataclass(frozen=True, slots=True)
class SweepResult:
    rows_written: int
    closing_rows: int
    skipped_by_reason: dict[str, int]
    credits: int

    @property
    def alerting_skips(self) -> int:
        """Skips that indicate a real upstream problem — never the routine ones."""
        return self.skipped_by_reason.get(NOT_INGESTED, 0)


def sweep(
    client: PostgrestClient,
    *,
    budget: OddsBudget,
    api_key: str,
    slate: Slate,
    sport: str,
    now: datetime,
    closing_external_ids: frozenset[str] = frozenset(),
    endpoint_label: str = "odds/mlb",
    http: httpx.Client | None = None,
) -> SweepResult:
    """Take one snapshot and persist it. `fetch_odds` charges the budget itself."""
    payload = fetch_odds(api_key=api_key, budget=budget, client=http, endpoint_label=endpoint_label)
    archive_odds_payload(
        client, payload, entity_id=f"{now.isoformat()}/{endpoint_label}", pulled_at_utc=now
    )

    closing_payload, regular_payload = _partition(payload, slate, closing_external_ids)
    resolve = slate.resolver()
    closing = normalize_snapshot(
        closing_payload, resolve_game_id=resolve, captured_at_utc=now, is_closing=True
    )
    regular = normalize_snapshot(
        regular_payload, resolve_game_id=resolve, captured_at_utc=now, is_closing=False
    )
    rows = [_store_row(row, sport) for part in (closing, regular) for row in part.rows]
    insert_line_snapshots(client, rows)
    return SweepResult(
        rows_written=len(rows),
        closing_rows=len(closing.rows),
        skipped_by_reason=_merge_skips([closing, regular]),
        credits=CREDITS_PER_SWEEP,
    )


def _partition(
    payload: list[dict], slate: Slate, closing_external_ids: frozenset[str]
) -> tuple[list[dict], list[dict]]:
    """Split the response into the games at their close and everything else.

    `normalize_snapshot` takes one `is_closing` for a whole payload, and the
    flag is what `pick_settlements.closing_prob` is later read by — so a sweep
    aimed at the 7pm cluster must not stamp the 10pm games as closed. Anything
    that doesn't resolve falls in the non-closing half; `normalize_snapshot`
    records why it was skipped either way.
    """
    if not closing_external_ids:
        return [], payload
    resolve = build_external_game_id_resolver(slate.games)
    closing, regular = [], []
    for game in payload:
        resolution = resolve(
            str(game.get("home_team", "")), str(game.get("away_team", "")), _commence(game)
        )
        in_window = (
            isinstance(resolution, ResolvedExternalId)
            and resolution.external_id in closing_external_ids
        )
        (closing if in_window else regular).append(game)
    return closing, regular


def _commence(game: dict) -> datetime:
    """The external resolver ignores this argument (its index is one slate
    date), so a missing/odd `commence_time` must not be able to raise here."""
    return datetime.min


def _merge_skips(parts: list[NormalizedSnapshot]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for part in parts:
        for reason, count in part.skipped_by_reason.items():
            merged[reason] = merged.get(reason, 0) + count
    return merged


def _store_row(row: NormalizedRow, sport: str) -> LineSnapshotRow:
    """`odds/snapshot`'s row -> `store`'s row. Same fields plus `sport`, which
    `line_snapshots` carries for the (sport, market) FK into `sport_markets`."""
    return LineSnapshotRow(
        game_id=row.game_id,
        sport=sport,
        market=row.market,
        side=row.side,
        price_american=row.price_american,
        captured_at_utc=row.captured_at_utc,
        line=row.line,
        implied_prob_devigged=row.implied_prob_devigged,
        devig_method=row.devig_method,
        source=row.source,
        is_closing=row.is_closing,
    )


def assert_slate_integrity(
    result: SweepResult, *, threshold: int = NOT_INGESTED_ALERT_THRESHOLD
) -> None:
    """Raise when a sweep's `NOT_INGESTED` count crosses the alert threshold.

    Called *after* the rows are written and the credits are spent, deliberately:
    the snapshot itself is good and worth keeping, and failing the workflow is
    how backend doc §2.4's failure handling (the workflow-failure email) reaches
    an operator. Re-running costs another 3 credits out of §2.5's ~50/month
    retry headroom, which is the intended price of noticing.
    """
    count = result.alerting_skips
    if count > threshold:
        raise SlateIntegrityError(
            f"{count} game(s) in the odds feed have no `games` row ({NOT_INGESTED}); "
            f"skips by reason: {result.skipped_by_reason}"
        )
