"""One file per market; each satisfies `sbm.contracts.market.Market`.

Adding a market means adding one file here that satisfies the protocol and
registering it in `MARKETS` — nothing else in the engine changes.
"""

from sbm.contracts.market import Market
from sbm.markets.moneyline import MoneylineMarket
from sbm.markets.prop import PropMarket
from sbm.markets.spread import SpreadMarket
from sbm.markets.total import TotalMarket

MARKETS: dict[str, type] = {
    m.key: m for m in (MoneylineMarket, TotalMarket, SpreadMarket, PropMarket)
}
"""Registry keyed by `Market.key`, for callers that look up a market plugin by
the string persisted in `picks.market`."""


def market_registry() -> dict[str, Market]:
    """Instantiated plugins keyed by `Market.key`.

    What `core.backtest.run_backtest` and `jobs/` want: markets are stateless,
    so one instance each is enough, and passing instances keeps `core` bound to
    the `Market` contract rather than to a registry of classes.
    """
    return {key: cls() for key, cls in MARKETS.items()}


__all__ = [
    "MARKETS",
    "MoneylineMarket",
    "PropMarket",
    "SpreadMarket",
    "TotalMarket",
    "market_registry",
]
