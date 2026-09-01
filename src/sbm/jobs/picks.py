"""Shaping a scored slate into `picks` rows: quote indexing, ids, versions.

Split out of `model_pass.py` so the orchestration there reads as the seven
steps it is. Everything here is translation — no pricing decision is made in
this file (that is `pricing.py`) and no probability is produced (that is
`scoring.py`).

The id boundary lives here. `scoring.py` and `features/` speak external gamePks
because a Postgres surrogate means nothing to a model (`contracts/feature.py`);
`picks.game_id` and `line_snapshots.game_id` are that surrogate. Both shapes
exist in this module and nowhere else.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime

from sbm.contracts.market import Market
from sbm.jobs.pricing import PricedPick, shared_line
from sbm.jobs.rpc import LineQuote
from sbm.jobs.scoring import QuotedLines
from sbm.store.client import PostgrestClient
from sbm.store.runs import PickRow

QuoteIndex = dict[str, dict[str, dict[str, LineQuote]]]
"""external_game_id -> market -> side -> the latest quote."""

def index_quotes(quotes: list[LineQuote], external_of: dict[int, str]) -> QuoteIndex:
    """Group flat `line_snapshots` rows by (game, market, side).

    A quote whose `game_id` is not on today's slate is dropped rather than
    keyed under a stray id: `fn_latest_lines` is filtered by slate date, so
    this only fires if the two disagree, and a pick priced from another day's
    line is worse than a pick that doesn't exist.
    """
    index: QuoteIndex = {}
    for quote in quotes:
        external_id = external_of.get(quote.game_id)
        if external_id is None:
            continue
        index.setdefault(external_id, {}).setdefault(quote.market, {})[quote.side] = quote
    return index


def line_index(index: QuoteIndex, markets: Mapping[str, Market]) -> QuotedLines:
    """(game, market) -> the line to score against, for fully-quoted markets.

    The line is `pricing.shared_line`'s resolved home-perspective number, not
    whichever side happened to come first out of the dict: a run line is stored
    -1.5 on the home row and +1.5 on the away row, and handing `+1.5` to
    `SpreadMarket.probability` prices the opposite of the intended side without
    raising.

    A one-sided quote, an unknown market, or a pair that is not one line is left
    out. Each cannot produce a pick anyway — de-vig needs the complementary
    pair, and `price_market` skips the rest — so scoring them would only spend
    Monte-Carlo draws on rows that never get written.
    """
    out: QuotedLines = {}
    for external_id, by_market in index.items():
        for market_key, sides in by_market.items():
            market = markets.get(market_key)
            if market is None or set(sides) != set(market.sides):
                continue
            resolved = shared_line(market, sides)
            if resolved is not None:
                out[(external_id, market_key)] = resolved.line
    return out


def to_pick_row(
    priced: PricedPick, *, game_id: int, game_date: date, locked_at: datetime
) -> PickRow:
    """One `PricedPick` -> the row `publish_run` sends to `fn_publish_run`.

    `devig_method` travels with `market_fair_prob` and is never omitted:
    `picks` carries `CHECK ((market_fair_prob IS NULL) = (devig_method IS
    NULL))` (003), and `PickRow.__post_init__` mirrors it so a mismatch names
    the field here instead of rolling back the whole slate's publish
    transaction in Postgres. The column exists because `picks` is append-only —
    a backtest has to be able to prove which method produced a stored number
    even after `markets.devig_method` changes, since history cannot be
    back-corrected.
    """
    return PickRow(
        game_id=game_id,
        game_date=game_date,
        market=priced.market,
        side=priced.side,
        raw_model_prob=priced.raw_model_prob,
        model_prob=priced.model_prob,
        recommended=priced.recommended,
        kelly_stake_fraction=priced.kelly_stake_fraction,
        pick_locked_at=locked_at,
        line=priced.line,
        market_fair_prob=priced.market_fair_prob,
        devig_method=priced.devig_method,
        market_odds_american=priced.market_odds_american,
        edge_pct=priced.edge_pct,
    )


def resolve_model_version(client: PostgrestClient, *, sport: str, git_sha: str) -> int:
    """`model_versions.id` for this commit, creating the row if it is new.

    `git_sha` is the canonical version key (backend doc §3.2) and the table is
    `UNIQUE (sport, git_sha)`, so this is an idempotent upsert rather than a
    read-then-insert race between two jobs on the same commit.
    """
    rows = client.upsert(
        "model_versions", [{"sport": sport, "git_sha": git_sha}], on_conflict="sport,git_sha"
    )
    return int(rows[0]["id"])
