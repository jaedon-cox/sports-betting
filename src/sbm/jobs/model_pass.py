"""The body Jobs C and D share: score the slate, price it, publish it atomically.

The two passes differ in exactly two things — `pass_type` and the instant they
run (backend doc §2.4: Pass A ~3h pre-game on projected lineups, Pass B ~T-45min
on confirmed ones). Everything else is identical by design, because a research
pass that priced differently from the official one would make the comparison
between them meaningless. So it lives here once.

**Prices come from the stored open snapshot, not a fresh call.** §2.5 affords 2
snapshots per game for the whole month; Job A bought the open and Job E buys the
close. A third call from each pass would be ~90 extra credits/month and put the
system 40 over the cap. `reads.latest_lines` is therefore an as-of read
(`captured_at_utc <= now`), which is also the only shape that keeps a re-run
honest.

**Publishing is one RPC, and the status flip is its last statement.** A pass
that dies at game 8 of 15 leaves its `model_runs` row short of `'success'`, so
`v_todays_picks` never sees it and the frontend keeps showing the last
known-good complete slate (§2.4). `publish_run` is idempotent against an
already-successful (version, date, pass) key, so a retry no-ops.

**Calibration is pass-through until settled history exists.** `calibrators` is
an argument, and an absent market means "score uncalibrated" — which
`core.backtest.calibrate` documents as the honest early state, not an error.
Model doc A5 requires the fit to come from a held-out *later* chronological
slice; there are no settled games yet, so fitting one now would be fitting on
nothing. `picks.raw_model_prob` and `picks.model_prob` are written either way.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from sbm.contracts.feature import AsOf, FeatureBuilder
from sbm.core.backtest.calibrate import apply
from sbm.core.calibration import Calibrator
from sbm.jobs.context import JobContext
from sbm.jobs.picks import index_quotes, line_index, resolve_model_version, to_pick_row
from sbm.jobs.pricing import PricedPick, price_market
from sbm.jobs.rpc import latest_lines
from sbm.jobs.scoring import score_slate
from sbm.jobs.slate_ingest import Slate
from sbm.markets import market_registry
from sbm.sports.mlb.vertical import MLBVertical
from sbm.store.runs import PickRow, publish_run

UNPRICED_MARKET = "unpriced_market"
"""A quoted market this sport vertical does not price."""


@dataclass(frozen=True, slots=True)
class PassResult:
    model_run_id: int
    n_games: int
    n_picks: int
    n_recommended: int
    skipped: dict[str, int]


def run_pass(
    ctx: JobContext,
    slate: Slate,
    *,
    pass_type: str,
    builder: FeatureBuilder | None = None,
    calibrators: Mapping[str, Calibrator] | None = None,
) -> PassResult:
    """Score, price and publish one pass over `slate`. Returns what it wrote."""
    vertical = MLBVertical()
    markets = {k: m for k, m in market_registry().items() if k in vertical.market_keys}
    external_of = {internal: external for external, internal in slate.game_ids.items()}

    quotes = index_quotes(
        latest_lines(
            ctx.client, sport=ctx.config.sport, game_date=slate.slate_date, as_of=ctx.now
        ),
        external_of,
    )
    lines = line_index(quotes, markets)
    raw = score_slate(
        vertical,
        markets,
        game_ids=[gid for gid in slate.external_ids if gid in quotes],
        lines=lines,
        as_of=AsOf(ts=ctx.now),
        n_draws=ctx.config.n_draws,
        rng=np.random.default_rng(_seed(ctx, slate, pass_type)),
        builder=builder,
    )

    rows: list[PickRow] = []
    skipped: dict[str, int] = {}
    for external_id, by_market in quotes.items():
        for market_key, sides in by_market.items():
            market = markets.get(market_key)
            if market is None:
                # A stored line for a market this vertical does not price. Data,
                # not an error (CLAUDE.md rule 7) — counted and moved past.
                skipped[UNPRICED_MARKET] = skipped.get(UNPRICED_MARKET, 0) + 1
                continue
            raw_probs = {
                side: raw[(external_id, market_key, side)]
                for side in market.sides
                if (external_id, market_key, side) in raw
            }
            calibrator = (calibrators or {}).get(market_key)
            model_probs = {side: apply(calibrator, prob) for side, prob in raw_probs.items()}
            priced = price_market(
                market,
                sides,
                model_probs,
                raw_probs,
                edge_threshold=ctx.config.edge_threshold,
                kelly_fraction=ctx.config.kelly_fraction,
            )
            if not isinstance(priced, PricedPick):
                skipped[priced.reason] = skipped.get(priced.reason, 0) + 1
                continue
            rows.append(
                to_pick_row(
                    priced,
                    game_id=slate.game_ids[external_id],
                    game_date=slate.slate_date,
                    locked_at=ctx.now,
                )
            )

    model_run_id = publish_run(
        ctx.client,
        model_version_id=resolve_model_version(
            ctx.client, sport=ctx.config.sport, git_sha=ctx.config.git_sha
        ),
        sport=ctx.config.sport,
        run_date=slate.slate_date,
        pass_type=pass_type,
        picks=rows,
        github_run_id=ctx.config.github_run_id,
    )
    return PassResult(
        model_run_id=model_run_id,
        n_games=len(slate.games),
        n_picks=len(rows),
        n_recommended=sum(1 for row in rows if row.recommended),
        skipped=skipped,
    )


def _seed(ctx: JobContext, slate: Slate, pass_type: str) -> int:
    """A seed derived from (sport, slate date, pass) rather than the clock.

    Monte-Carlo draws must reproduce (CLAUDE.md conventions), and a re-run after
    a failed publish should price the same slate the same way rather than
    producing a second, subtly different set of numbers for the same day.
    """
    key = f"{ctx.config.sport}:{slate.slate_date.isoformat()}:{pass_type}".encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")
