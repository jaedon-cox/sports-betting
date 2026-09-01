"""What `score_slate` scores, and what it refuses to.

Exercised against a stub vertical throughout: the assertions worth making here
are about which (game, market, side) triples get a probability at all, and that
is line-index and dimension logic, not run distributions. The stubs are shared
with `test_model_pass.py`, which covers the same seam through the real model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from sbm.contracts.feature import AsOf
from sbm.jobs.scoring import score_slate
from sbm.markets import market_registry

NOW = datetime(2026, 7, 1, 22, 45, tzinfo=UTC)
AS_OF = AsOf(ts=NOW)


# --------------------------------------------------------------------------
# stubs
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StubDistribution:
    """Draws that are constant per game, so a probability is a step function of
    the line and every assertion below is exact rather than statistical."""

    home_runs: float
    away_runs: float
    n_dims: int = 2

    def sample(self, n_draws: int, rng: np.random.Generator) -> np.ndarray:
        rng.random()  # consume, so "same seed -> same slate" is a real claim
        return np.tile([self.home_runs, self.away_runs], (n_draws, 1)).astype(np.float64)


@dataclass(frozen=True)
class StubVertical:
    key: str = "stub"
    market_keys: tuple[str, ...] = ("moneyline", "total", "spread")
    n_dims: int = 2

    def feature_builder(self) -> object:
        raise AssertionError("run_pass/score_slate must use the injected builder")

    def distribution(self, features: pd.Series) -> StubDistribution:
        return StubDistribution(
            home_runs=float(features["home_runs"]),
            away_runs=float(features["away_runs"]),
            n_dims=self.n_dims,
        )


@dataclass(frozen=True)
class StubBuilder:
    """A `FeatureBuilder` that hands back a fixed frame and records its call."""

    frame: pd.DataFrame
    calls: list[tuple[list[str], AsOf]]

    def build(self, game_ids: list[str], as_of: AsOf) -> pd.DataFrame:
        self.calls.append((game_ids, as_of))
        return self.frame.reindex(game_ids)


def stub_builder(*game_ids: str, home: float = 5.0, away: float = 3.0) -> StubBuilder:
    frame = pd.DataFrame(
        {"home_runs": home, "away_runs": away}, index=pd.Index(list(game_ids))
    )
    return StubBuilder(frame=frame, calls=[])


# --------------------------------------------------------------------------
# score_slate
# --------------------------------------------------------------------------


def test_only_markets_with_a_quoted_line_are_scored() -> None:
    """An unquoted market costs Monte-Carlo draws for a pick that can never be
    priced — `pricing` needs two sides to de-vig, so it would skip it anyway."""
    probs = score_slate(
        StubVertical(),
        market_registry(),
        game_ids=["1"],
        lines={("1", "total"): 8.5},
        as_of=AS_OF,
        n_draws=16,
        rng=np.random.default_rng(0),
        builder=stub_builder("1"),
    )
    assert {key[1] for key in probs} == {"total"}
    assert set(probs) == {("1", "total", "over"), ("1", "total", "under")}


def test_a_moneyline_key_present_with_a_none_line_is_still_scored() -> None:
    """Moneyline's line is legitimately NULL; membership in the index is the
    test, not truthiness of the value."""
    probs = score_slate(
        StubVertical(),
        market_registry(),
        game_ids=["1"],
        lines={("1", "moneyline"): None},
        as_of=AS_OF,
        n_draws=16,
        rng=np.random.default_rng(0),
        builder=stub_builder("1"),
    )
    assert probs[("1", "moneyline", "home")] == 1.0  # 5 > 3 on every draw
    assert probs[("1", "moneyline", "away")] == 0.0


def test_the_whole_slate_is_built_at_one_as_of_in_a_single_call() -> None:
    """Batching must not hand one game a frame built at another's instant."""
    builder = stub_builder("1", "2", "3")
    score_slate(
        StubVertical(),
        market_registry(),
        game_ids=["1", "2", "3"],
        lines={(g, "total"): 8.5 for g in ("1", "2", "3")},
        as_of=AS_OF,
        n_draws=16,
        rng=np.random.default_rng(0),
        builder=builder,
    )
    assert len(builder.calls) == 1
    assert builder.calls[0] == (["1", "2", "3"], AS_OF)


def test_a_market_needing_more_dimensions_than_the_sport_produces_raises() -> None:
    """A 1-column prop distribution cannot answer a team market; that is a
    wiring bug, not a data gap, so it must not be silently skipped."""
    with pytest.raises(ValueError, match="needs 2-dim draws"):
        score_slate(
            StubVertical(n_dims=1),
            market_registry(),
            game_ids=["1"],
            lines={("1", "total"): 8.5},
            as_of=AS_OF,
            n_draws=16,
            rng=np.random.default_rng(0),
            builder=stub_builder("1"),
        )


def test_the_same_seed_reproduces_the_same_slate() -> None:
    """CLAUDE.md conventions: every Monte-Carlo result is reproducible."""
    kwargs = dict(
        game_ids=["1", "2"],
        lines={("1", "total"): 8.5, ("2", "total"): 8.5},
        as_of=AS_OF,
        n_draws=64,
        builder=stub_builder("1", "2"),
    )
    first = score_slate(
        StubVertical(), market_registry(), rng=np.random.default_rng(7), **kwargs
    )
    second = score_slate(
        StubVertical(), market_registry(), rng=np.random.default_rng(7), **kwargs
    )
    assert first == second
