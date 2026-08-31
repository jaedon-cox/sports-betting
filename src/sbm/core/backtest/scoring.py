"""Point-in-time model probabilities for every quoted (market, side).

Scoring goes through the `SportVertical` / `FeatureBuilder` protocols and
nothing else — there is deliberately no backtest-only feature path. That is the
whole content of rule 4: a backtest that could build features its own way would
be reporting CLV for a model that never ran in production.

Market odds are absent from this module's inputs by construction (A1) — quotes
are read only for the line each market is priced at, never as a feature.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from numpy.random import Generator

from sbm.contracts.feature import AsOf
from sbm.contracts.market import Market
from sbm.contracts.sport import SportVertical
from sbm.core.backtest.types import BacktestGame

RawProbs = dict[tuple[str, str, str], float]
"""(game_id, market_key, side) -> pre-calibration P(side covers)."""


def quoted_lines(game: BacktestGame) -> dict[str, float | None]:
    """The single line each quoted market is priced at.

    Both sides of a market must carry the *same* number: a spread's line is
    always written from the home team's perspective regardless of which side is
    queried (`markets/spread.py`), so a book's "home -1.5 / away +1.5" must
    arrive here as -1.5 on both quotes. A sign-flipped away line would silently
    price the wrong side, so it is an error rather than a normalization we guess
    at.

    A game with no quotes at all is an error, not an empty result. That is what
    an unresolved id join looks like — the games are there, the odds rows came
    back empty — and left alone it produces a report of zero picks and a NaN
    CLV rather than a failure.
    """
    if not game.quotes:
        raise ValueError(
            f"{game.game_id} has no quotes; a game with no market to price cannot be "
            "evaluated (check the game-id join)"
        )
    lines: dict[str, float | None] = {}
    for quote in game.quotes:
        if quote.market in lines and lines[quote.market] != quote.line:
            raise ValueError(
                f"{game.game_id}/{quote.market}: sides quote different lines "
                f"({lines[quote.market]} vs {quote.line}); lines are home-perspective "
                "and shared across sides"
            )
        lines[quote.market] = quote.line
    return lines


def raw_probabilities(
    vertical: SportVertical,
    markets: Mapping[str, Market],
    games: Sequence[BacktestGame],
    *,
    n_draws: int,
    rng: Generator,
) -> RawProbs:
    """Score every quoted side of every game at that game's own `as_of`.

    Games sharing an identical `as_of` are built in one `FeatureBuilder.build`
    call. Batching is allowed *within* a timestamp and never across one — a
    batch spanning two timestamps would hand the earlier game a frame built at
    the later instant.

    `rng` is consumed in the given game order, so results reproduce exactly for
    a fixed seed and ordering; `engine.py` sorts chronologically before calling,
    which also makes the draws independent of how folds are cut.
    """
    builder = vertical.feature_builder()
    out: RawProbs = {}
    for as_of, batch in _group_by_as_of(games).items():
        frame = builder.build([game.game_id for game in batch], as_of)
        for game in batch:
            distribution = vertical.distribution(frame.loc[game.game_id])
            draws = distribution.sample(n_draws, rng)
            for market_key, line in quoted_lines(game).items():
                market = _lookup(markets, market_key, game.game_id)
                if market.required_dims != distribution.n_dims:
                    raise ValueError(
                        f"{game.game_id}/{market_key} needs {market.required_dims}-dim draws "
                        f"but {vertical.key} produced {distribution.n_dims}"
                    )
                for side in market.sides:
                    out[(game.game_id, market_key, side)] = market.probability(draws, side, line)
    return out


def _group_by_as_of(games: Sequence[BacktestGame]) -> dict[AsOf, list[BacktestGame]]:
    groups: dict[AsOf, list[BacktestGame]] = {}
    for game in games:
        groups.setdefault(game.as_of, []).append(game)
    return groups


def _lookup(markets: Mapping[str, Market], market_key: str, game_id: str) -> Market:
    if market_key not in markets:
        raise KeyError(
            f"{game_id} quotes market {market_key!r} with no plugin in the registry "
            f"({sorted(markets)})"
        )
    return markets[market_key]
