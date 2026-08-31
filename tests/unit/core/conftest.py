"""Shared fakes for the `core` suite.

A fake `SportVertical` rather than MLB's: `core` may never import
`sbm.sports.*` (rule 2), and its tests shouldn't either, or the tests become
the back door the architecture test was written to close.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from numpy.random import Generator, default_rng

from sbm.contracts.feature import AsOf
from sbm.contracts.market import MarketQuote
from sbm.core.backtest import BacktestGame
from sbm.markets import market_registry

START = datetime(2024, 4, 1, 23, 0, tzinfo=UTC)


@dataclass
class PoissonPair:
    """Two independent Poisson run counts — a stand-in for the NB joint dist."""

    home_mu: float
    away_mu: float
    n_dims: int = 2

    def sample(self, n: int, rng: Generator) -> np.ndarray:
        pair = [rng.poisson(self.home_mu, n), rng.poisson(self.away_mu, n)]
        return np.column_stack(pair).astype(np.float64)


class RecordingFeatureBuilder:
    """Records every (game_ids, as_of) it was asked for, so tests can assert the
    engine batched only within a timestamp and never across one."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], datetime]] = []

    def build(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame:
        self.calls.append((tuple(game_ids), as_of.ts))
        strength = np.array([_strength(gid) for gid in game_ids], dtype=np.float64)
        return pd.DataFrame({"home_mu": 4.5 + strength, "away_mu": 4.5 - strength}, index=game_ids)


class FakeVertical:
    key = "fake"
    market_keys = ("moneyline", "total")

    def __init__(self) -> None:
        self.builder = RecordingFeatureBuilder()

    def feature_builder(self) -> RecordingFeatureBuilder:
        return self.builder

    def distribution(self, features: pd.Series) -> PoissonPair:
        return PoissonPair(home_mu=float(features["home_mu"]), away_mu=float(features["away_mu"]))


def _strength(game_id: str) -> float:
    """Deterministic per-game home edge in runs, spread over [-1, 1)."""
    return (int(game_id.removeprefix("g")) % 21 - 10) / 10.0


def quotes(market: str, prices: dict[str, int], line: float | None = None) -> list[MarketQuote]:
    return [
        MarketQuote(market=market, side=side, line=line, price_american=price)
        for side, price in prices.items()
    ]


def make_game(
    game_id: str = "g001",
    *,
    ts: datetime | None = None,
    bet: dict[str, int] | None = None,
    close: dict[str, int] | None = None,
    outcome: tuple[float, float] = (5.0, 3.0),
    market: str = "moneyline",
    line: float | None = None,
) -> BacktestGame:
    bet = bet or {"home": -150, "away": 130}
    close = close or {"home": -170, "away": 145}
    return BacktestGame(
        game_id=game_id,
        as_of=AsOf(ts=ts or START),
        quotes=tuple(quotes(market, bet, line)),
        closing_quotes=tuple(quotes(market, close, line)),
        outcome=np.array([outcome], dtype=np.float64),
    )


def season(n_games: int, *, rng: Generator | None = None) -> list[BacktestGame]:
    """`n_games` moneyline games, one per day, outcomes drawn from the same
    Poisson means the fake vertical models — so the model is well specified and
    a walk-forward over it should show near-zero calibration error."""
    rng = rng or default_rng(7)
    games = []
    for i in range(n_games):
        game_id = f"g{i:04d}"
        strength = _strength(game_id)
        home, away = rng.poisson(4.5 + strength), rng.poisson(4.5 - strength)
        while home == away:  # baseball has no ties; keep settlement binary
            home, away = rng.poisson(4.5 + strength), rng.poisson(4.5 - strength)
        games.append(
            make_game(
                game_id,
                ts=START + timedelta(days=i),
                bet={"home": -130 - int(strength * 60), "away": 115 + int(strength * 55)},
                close={"home": -134 - int(strength * 60), "away": 118 + int(strength * 55)},
                outcome=(float(home), float(away)),
            )
        )
    return games


@pytest.fixture
def markets() -> dict:
    return market_registry()


@pytest.fixture
def vertical() -> FakeVertical:
    return FakeVertical()
