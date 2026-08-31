"""backtest/scoring.py: point-in-time scoring through the public protocols.

The leakage-relevant assertions are the batching ones: a `FeatureBuilder.build`
call must never span two `as_of` timestamps, or the earlier game gets a frame
built at the later instant (rule 4).
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest
from conftest import START, FakeVertical, make_game
from numpy.random import default_rng

from sbm.contracts.market import MarketQuote
from sbm.core.backtest import quoted_lines, raw_probabilities


def test_scores_every_side_of_every_quoted_market(vertical: FakeVertical, markets: dict) -> None:
    game = make_game("g001")
    probs = raw_probabilities(vertical, markets, [game], n_draws=2000, rng=default_rng(0))
    assert set(probs) == {("g001", "moneyline", "home"), ("g001", "moneyline", "away")}
    assert all(0.0 <= p <= 1.0 for p in probs.values())


def test_complementary_sides_sum_to_at_most_one(vertical: FakeVertical, markets: dict) -> None:
    game = make_game(
        "g001",
        market="total",
        line=8.5,
        bet={"over": -110, "under": -110},
        close={"over": -115, "under": -105},
    )
    probs = raw_probabilities(vertical, markets, [game], n_draws=5000, rng=default_rng(0))
    assert sum(probs.values()) <= 1.0 + 1e-9


def test_builds_are_batched_within_a_timestamp(vertical: FakeVertical, markets: dict) -> None:
    games = [make_game(f"g{i:03d}", ts=START) for i in range(3)]
    raw_probabilities(vertical, markets, games, n_draws=100, rng=default_rng(0))
    assert vertical.builder.calls == [(("g000", "g001", "g002"), START)]


def test_builds_never_span_two_timestamps(vertical: FakeVertical, markets: dict) -> None:
    later = START + timedelta(days=1)
    games = [make_game("g000", ts=START), make_game("g001", ts=later)]
    raw_probabilities(vertical, markets, games, n_draws=100, rng=default_rng(0))
    assert vertical.builder.calls == [(("g000",), START), (("g001",), later)]


def test_each_game_is_scored_at_its_own_as_of(vertical: FakeVertical, markets: dict) -> None:
    games = [make_game("g000", ts=START), make_game("g001", ts=START + timedelta(days=5))]
    raw_probabilities(vertical, markets, games, n_draws=100, rng=default_rng(0))
    assert [ts for _, ts in vertical.builder.calls] == [g.as_of.ts for g in games]


def test_scoring_is_reproducible_for_a_fixed_seed(vertical: FakeVertical, markets: dict) -> None:
    games = [make_game(f"g{i:03d}", ts=START) for i in range(3)]
    first = raw_probabilities(vertical, markets, games, n_draws=1000, rng=default_rng(11))
    second = raw_probabilities(FakeVertical(), markets, games, n_draws=1000, rng=default_rng(11))
    assert first == second


def test_quoted_lines_reads_one_line_per_market() -> None:
    game = make_game(
        "g001",
        market="total",
        line=8.5,
        bet={"over": -110, "under": -110},
        close={"over": -110, "under": -110},
    )
    assert quoted_lines(game) == {"total": 8.5}


def test_sign_flipped_away_line_is_an_error() -> None:
    """A book's "home -1.5 / away +1.5" must reach the engine as -1.5 on both
    sides; silently accepting the flip would price the wrong side."""
    game = make_game(
        "g001",
        market="spread",
        line=-1.5,
        bet={"home": -110, "away": -110},
        close={"home": -110, "away": -110},
    )
    flipped = game.quotes[0], MarketQuote(
        market="spread", side="away", line=1.5, price_american=-110
    )
    with pytest.raises(ValueError, match="different lines"):
        quoted_lines(
            type(game)(
                game_id=game.game_id,
                as_of=game.as_of,
                quotes=flipped,
                closing_quotes=game.closing_quotes,
                outcome=game.outcome,
            )
        )


def test_unknown_market_key_is_a_clear_error(vertical: FakeVertical) -> None:
    game = make_game(
        "g001",
        market="first_five",
        bet={"home": -110, "away": -110},
        close={"home": -110, "away": -110},
    )
    with pytest.raises(KeyError, match="no plugin in the registry"):
        raw_probabilities(vertical, {}, [game], n_draws=10, rng=default_rng(0))


def test_dimension_mismatch_between_vertical_and_market(
    vertical: FakeVertical, markets: dict
) -> None:
    """The fake vertical is 2-dim; pricing a 1-dim prop off it must fail loudly
    rather than read column 0 as a stat line."""
    game = make_game(
        "g001",
        market="prop",
        line=1.5,
        bet={"over": -110, "under": -110},
        close={"over": -110, "under": -110},
    )
    with pytest.raises(ValueError, match="needs 1-dim draws"):
        raw_probabilities(vertical, markets, [game], n_draws=10, rng=default_rng(0))


def test_a_stronger_home_team_gets_a_higher_probability(
    vertical: FakeVertical, markets: dict
) -> None:
    """Sanity that features actually reach the distribution: `g010` has the
    biggest home edge in the fake vertical, `g000` the smallest."""
    games = [make_game("g000", ts=START), make_game("g010", ts=START)]
    probs = raw_probabilities(vertical, markets, games, n_draws=20000, rng=default_rng(3))
    assert probs[("g010", "moneyline", "home")] > probs[("g000", "moneyline", "home")]
    assert np.isfinite(probs[("g000", "moneyline", "home")])


def test_a_game_with_no_quotes_is_an_error(vertical: FakeVertical, markets: dict) -> None:
    """What an unresolved game-id join looks like: the games are there, the odds
    rows came back empty. Left alone it reports zero picks and a NaN CLV instead
    of failing, so it has to raise."""
    game = make_game("g001")
    unquoted = type(game)(
        game_id=game.game_id,
        as_of=game.as_of,
        quotes=(),
        closing_quotes=(),
        outcome=game.outcome,
    )
    with pytest.raises(ValueError, match="no quotes"):
        raw_probabilities(vertical, markets, [unquoted], n_draws=10, rng=default_rng(0))
