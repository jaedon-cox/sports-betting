"""Conformance suite every `Market` implementation must pass."""

from __future__ import annotations

import pytest
from market_conformance import assert_market_conforms
from numpy.random import default_rng

from sbm.markets import MARKETS


@pytest.mark.contract
@pytest.mark.parametrize("market_cls", MARKETS.values(), ids=MARKETS.keys())
def test_market_conforms(market_cls: type) -> None:
    assert_market_conforms(market_cls(), default_rng(seed=42))
