"""Live slate scoring: features at an `as_of` -> draws -> raw market probabilities.

The live twin of `core.backtest.scoring`, which cannot be reused directly
because it consumes `BacktestGame` (a settled row with a realized outcome and a
closing quote — none of which exist at pick time). What it *can* share is the
part that matters: this module goes through the same `SportVertical` /
`FeatureBuilder` protocols, at the same `AsOf`, and asks the same market
plugins for the same probability. Rule 4's "the same builder serves live and
backtest — do not fork them" is about the builder, and there is exactly one.

Market odds are not an input here (model doc A1). A quoted *line* is — a total
has no probability without a number to price against — but the price never
reaches the feature frame, only the edge layer in `pricing.py`.

`game_ids` are the sport's own external ids (MLB gamePk), never `games.id`:
`contracts/feature.py` is explicit that a storage surrogate means nothing to a
model. The internal id is re-attached in `model_pass.py`, at the store
boundary, where it belongs.
"""

from __future__ import annotations

from collections.abc import Mapping

from numpy.random import Generator

from sbm.contracts.feature import AsOf, FeatureBuilder
from sbm.contracts.market import Market
from sbm.contracts.sport import SportVertical

SlateProbs = dict[tuple[str, str, str], float]
"""(external_game_id, market_key, side) -> pre-calibration P(side covers)."""

QuotedLines = Mapping[tuple[str, str], float | None]
"""(external_game_id, market_key) -> the line both sides are quoted at."""


def score_slate(
    vertical: SportVertical,
    markets: Mapping[str, Market],
    *,
    game_ids: list[str],
    lines: QuotedLines,
    as_of: AsOf,
    n_draws: int,
    rng: Generator,
    builder: FeatureBuilder | None = None,
) -> SlateProbs:
    """Raw probabilities for every quoted (game, market, side) on the slate.

    One `FeatureBuilder.build` call for the whole slate: every game shares the
    run's single `as_of`, so batching cannot hand one game a frame built at
    another's instant (the constraint `core.backtest.scoring` enforces by
    grouping).

    `builder` is injectable because `MLBFeatureBuilder`'s default snapshot
    source is `_UnwiredSnapshotSource`, which raises rather than fabricating
    data. A job left on the default fails loudly and correctly until a real
    point-in-time `SnapshotSource` exists; passing one here is the whole wiring
    change when it does.

    `rng` is threaded explicitly (CLAUDE.md conventions) and consumed in
    `game_ids` order, so a fixed seed reproduces a slate exactly.
    """
    frame = (builder or vertical.feature_builder()).build(game_ids, as_of)
    out: SlateProbs = {}
    for game_id in game_ids:
        distribution = vertical.distribution(frame.loc[game_id])
        draws = distribution.sample(n_draws, rng)
        for market_key, market in markets.items():
            if (game_id, market_key) not in lines:
                continue  # no quote for this market on this game — nothing to price
            if market.required_dims != distribution.n_dims:
                raise ValueError(
                    f"{game_id}/{market_key} needs {market.required_dims}-dim draws but "
                    f"{vertical.key} produced {distribution.n_dims}"
                )
            line = lines[(game_id, market_key)]
            for side in market.sides:
                out[(game_id, market_key, side)] = market.probability(draws, side, line)
    return out
