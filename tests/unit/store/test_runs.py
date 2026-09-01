"""PickRow's de-vig provenance guard, and what publish_run sends over the wire.

`picks` is append-only, so a backtest has to be able to prove which de-vig
method produced a given `market_fair_prob` even after `markets.devig_method`
changes — which is why 003 pairs the two columns under a CHECK and why the row
class mirrors it. Failing here names the field; failing at the RPC is a
constraint violation that rolls back the whole slate, one line into a job that
had already priced fifteen games.

The `SettlementRow` half of the same pattern is in `test_facts.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from sbm.store.runs import PickRow, publish_run

GAME_DATE = date(2026, 7, 1)
LOCKED_AT = datetime(2026, 7, 1, 22, 45, tzinfo=UTC)


class _FakePostgrest:
    """Stands in for `sbm.store.client.PostgrestClient` — no network."""

    def __init__(self, result: int = 42) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._result = result

    def rpc(self, function_name: str, params: dict) -> int:
        self.calls.append((function_name, params))
        return self._result


def pick(**overrides) -> PickRow:
    row = {
        "game_id": 101,
        "game_date": GAME_DATE,
        "market": "moneyline",
        "side": "home",
        "raw_model_prob": 0.55,
        "model_prob": 0.54,
        "recommended": True,
        "kelly_stake_fraction": 0.012,
        "pick_locked_at": LOCKED_AT,
        "market_fair_prob": 0.52,
        "devig_method": "power",
        "market_odds_american": -120,
        "edge_pct": 0.038,
    }
    return PickRow(**{**row, **overrides})


def test_a_fair_prob_carries_the_method_that_produced_it() -> None:
    assert pick().devig_method == "power"


def test_a_fair_prob_without_its_method_is_refused() -> None:
    """The number would be unauditable the moment the configured default
    changes, and `picks` can never be corrected in place."""
    with pytest.raises(ValueError, match="must both be set or both be None"):
        pick(devig_method=None)


def test_a_method_without_a_fair_prob_is_refused() -> None:
    """The other direction of 003's CHECK — a method label describing nothing."""
    with pytest.raises(ValueError, match="must both be set or both be None"):
        pick(market_fair_prob=None)


def test_an_unpriced_pick_may_omit_both() -> None:
    """A scored-but-unquoted pick is a legitimate row: `recommended=false` rows
    are kept precisely so the record is not filtered to where the model already
    believed it had an edge."""
    row = pick(market_fair_prob=None, devig_method=None, market_odds_american=None, edge_pct=None)
    assert (row.market_fair_prob, row.devig_method) == (None, None)


def test_dates_and_instants_are_json_stringified_for_the_rpc() -> None:
    """`to_json` feeds a JSONB parameter; a `date` is not JSON-serialisable."""
    row = pick().to_json()
    assert row["game_date"] == "2026-07-01"
    assert row["pick_locked_at"] == LOCKED_AT.isoformat()


def test_publish_run_sends_one_call_with_the_whole_slate() -> None:
    """Atomicity comes from it being a single function body — one implicit
    transaction — not from a client-managed BEGIN/COMMIT (§2.4)."""
    client = _FakePostgrest()
    run_id = publish_run(
        client,  # type: ignore[arg-type]
        model_version_id=3,
        sport="mlb",
        run_date=GAME_DATE,
        pass_type="confirmed",
        picks=[pick(game_id=101), pick(game_id=102)],
        github_run_id="99",
    )
    assert run_id == 42
    assert len(client.calls) == 1
    name, params = client.calls[0]
    assert name == "fn_publish_run"
    assert params["p_run_date"] == "2026-07-01"
    assert params["p_pass_type"] == "confirmed"
    assert params["p_github_run_id"] == "99"
    assert [p["game_id"] for p in params["p_picks"]] == [101, 102]


def test_an_empty_slate_still_publishes_a_run() -> None:
    """The status flip is the function's last statement, so a day with no
    picks must still close its run rather than leave yesterday's latest
    successful run looking like today's."""
    client = _FakePostgrest()
    assert publish_run(
        client,  # type: ignore[arg-type]
        model_version_id=3, sport="mlb", run_date=GAME_DATE,
        pass_type="confirmed", picks=[],
    ) == 42
    assert client.calls[0][1]["p_picks"] == []
