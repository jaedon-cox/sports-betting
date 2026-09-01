"""`run_pass` — the whole of what Jobs C and D do once a slate exists.

Run against the real `MLBVertical` over an injected feature frame, because the
seam worth pinning is exactly that: an injected `builder=` must reach the model
without `_UnwiredSnapshotSource` ever being constructed. The scoring stubs come
from `test_scoring.py`, which covers the layer underneath.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from sbm.jobs.model_pass import UNPRICED_MARKET, run_pass
from sbm.jobs.slate_ingest import Slate
from sbm.sports.mlb.model.columns import extract_side_inputs
from sbm.sports.mlb.vertical import MLBVertical
from tests.unit.jobs.fakes import FakeClient, make_context
from tests.unit.jobs.test_odds_sweep import game
from tests.unit.jobs.test_scoring import StubBuilder

NOW = datetime(2026, 7, 1, 22, 45, tzinfo=UTC)
SLATE_DATE = date(2026, 7, 1)

# --------------------------------------------------------------------------
# run_pass
# --------------------------------------------------------------------------

_NEUTRAL_COLUMNS = [
    f"{stem}_{side}"
    for stem in (
        "off_wrc_plus",
        "off_xwoba_vs_opp_hand",
        "starter_siera",
        "bullpen_xfip",
        "bullpen_fatigue",
        "starter_csw_pct",
        "starter_gb_pct",
    )
    for side in ("home", "away")
]


def neutral_builder(*game_ids: str) -> StubBuilder:
    """Every model column present and NaN — `columns._or_default` then falls back
    to the league-average prior, which is the documented behaviour for a missing
    source (doc §5.4) and keeps this test about wiring, not about the mean model.
    """
    frame = pd.DataFrame(
        {column: np.nan for column in _NEUTRAL_COLUMNS}, index=pd.Index(list(game_ids))
    )
    return StubBuilder(frame=frame, calls=[])


def test_the_neutral_frame_satisfies_every_column_the_model_reads() -> None:
    """Guards the fixture itself: `columns._raw` raises on a missing column, so a
    rename in `model/` must fail here loudly rather than make the tests below
    vacuous."""
    row = neutral_builder("1").frame.loc["1"]
    for side in ("home", "away"):
        assert extract_side_inputs(row, side).is_home == (side == "home")


def line_row(game_id: int, market: str, side: str, line: float | None, price: int) -> dict:
    return {
        "game_id": game_id,
        "market": market,
        "side": side,
        "line": line,
        "price_american": price,
        "implied_prob_devigged": None,
        "devig_method": None,
        "captured_at_utc": NOW.isoformat(),
        "is_closing": False,
    }


def make_slate_stub(game_ids: dict[str, int]) -> Slate:
    """`external_ids` (and therefore what gets scored) comes off `games`, not
    off the id map — a game missing from the schedule list is never priced even
    if a line for it is stored."""
    return Slate(
        slate_date=SLATE_DATE,
        games=[game(int(external), "HOM", "AWY") for external in game_ids],
        game_ids=game_ids,
        team_ids={},
    )


def context_with_lines(rows: list[dict]) -> tuple[FakeClient, object]:
    client = FakeClient(rpc_results={"fn_latest_lines": rows, "fn_publish_run": 42})
    return client, make_context(client, now=NOW)


def test_run_pass_prices_an_injected_frame_and_publishes_one_atomic_run() -> None:
    rows = [
        line_row(101, "moneyline", "home", None, -120),
        line_row(101, "moneyline", "away", None, 100),
    ]
    client, ctx = context_with_lines(rows)
    slate = make_slate_stub({"555": 101})

    result = run_pass(ctx, slate, pass_type="confirmed", builder=neutral_builder("555"))

    assert result.model_run_id == 42
    assert result.n_picks == 1
    published = dict(client.rpcs)["fn_publish_run"]
    assert published["p_pass_type"] == "confirmed"
    assert published["p_run_date"] == SLATE_DATE.isoformat()
    pick = published["p_picks"][0]
    assert pick["game_id"] == 101  # the surrogate, re-attached at the store boundary
    assert (pick["market"], pick["book"]) == ("moneyline", "pinnacle")


def test_a_stored_line_for_an_unpriced_market_is_counted_not_dropped() -> None:
    """CLAUDE.md rule 7 — a market this vertical does not price is data, not an
    error, and it must still show up in the run summary."""
    rows = [
        line_row(101, "moneyline", "home", None, -120),
        line_row(101, "moneyline", "away", None, 100),
        line_row(101, "first_inning_nrfi", "yes", None, -130),
        line_row(101, "first_inning_nrfi", "no", None, 110),
    ]
    client, ctx = context_with_lines(rows)
    result = run_pass(
        ctx, make_slate_stub({"555": 101}), pass_type="projected",
        builder=neutral_builder("555"),
    )
    assert result.skipped[UNPRICED_MARKET] == 1
    assert result.n_picks == 1


def test_a_one_sided_quote_is_skipped_with_its_reason() -> None:
    rows = [line_row(101, "moneyline", "home", None, -120)]
    client, ctx = context_with_lines(rows)
    result = run_pass(
        ctx, make_slate_stub({"555": 101}), pass_type="confirmed",
        builder=neutral_builder("555"),
    )
    assert result.n_picks == 0
    assert sum(result.skipped.values()) == 1


def test_latest_lines_is_read_as_of_the_run_instant() -> None:
    """A pick priced against a snapshot taken after it locked has meaningless
    CLV (backend doc §3.2)."""
    client, ctx = context_with_lines([])
    run_pass(ctx, make_slate_stub({}), pass_type="confirmed", builder=neutral_builder())
    assert dict(client.rpcs)["fn_latest_lines"]["p_as_of"] == NOW.isoformat()


def test_a_pass_over_an_empty_board_still_publishes_an_empty_successful_run() -> None:
    """`v_todays_picks` reads the latest *successful* run; a day with no quotes
    must close its run rather than leave yesterday's looking like today's."""
    client, ctx = context_with_lines([])
    result = run_pass(ctx, make_slate_stub({}), pass_type="confirmed", builder=neutral_builder())
    assert (result.n_picks, result.n_recommended) == (0, 0)
    assert dict(client.rpcs)["fn_publish_run"]["p_picks"] == []


def test_the_seed_is_derived_from_the_slate_not_the_clock() -> None:
    """A re-run after a failed publish must price the same slate identically
    rather than produce a second, subtly different set of numbers."""
    from sbm.jobs.model_pass import _seed

    slate = make_slate_stub({})
    ctx_a = make_context(now=NOW)
    ctx_b = make_context(now=NOW.replace(hour=3))
    assert _seed(ctx_a, slate, "confirmed") == _seed(ctx_b, slate, "confirmed")
    assert _seed(ctx_a, slate, "confirmed") != _seed(ctx_a, slate, "projected")


def test_run_pass_uses_the_real_vertical_when_a_builder_is_injected() -> None:
    """The whole point of the `builder=` seam: `_UnwiredSnapshotSource` must never
    be reached, so this must not raise NotImplementedError."""
    rows = [
        line_row(101, "total", "over", 8.5, -105),
        line_row(101, "total", "under", 8.5, -115),
    ]
    client, ctx = context_with_lines(rows)
    result = run_pass(
        ctx, make_slate_stub({"555": 101}), pass_type="confirmed",
        builder=neutral_builder("555"),
    )
    assert result.n_picks == 1
    assert isinstance(MLBVertical().distribution(neutral_builder("555").frame.loc["555"]).n_dims, int)
