"""The SQL read functions must return every column `pitching_rates` reads.

This exists because they did not. `fn_bullpen_game_form` aggregated eleven
counting stats and omitted `csw`, which surfaced in production as a bare
`KeyError: 'csw'` raised three frames deep inside `recency.py` — after the
slate had been ingested and with nothing in the message naming the SQL as the
cause.

Nothing else can catch this class of bug. The boundary is a Postgres
`RETURNS TABLE` on one side and a pandas column read on the other, so no type
checker sees it, and a unit test that feeds the reader a hand-built frame
proves only that the hand-built frame was right. The check has to be against
the migration text itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sbm.sports.mlb.features.source.rates import REQUIRED_COLUMNS

MIGRATION = Path(__file__).resolve().parents[3] / "db" / "migrations" / "018_feature_reads.sql"

RATE_FUNCTIONS = ("fn_pitcher_game_form", "fn_bullpen_game_form")
"""The two functions whose rows reach `pitching_rates`. `fn_team_batting_form`
feeds `batting_xwoba` instead and has its own, smaller contract."""


def returns_table_columns(function_name: str) -> set[str]:
    """Column names from a function's `RETURNS TABLE (...)` block."""
    text = MIGRATION.read_text()
    after = text.split(f"FUNCTION {function_name}", 1)[1]
    block = after.split("RETURNS TABLE", 1)[1].split(")", 1)[0]
    return set(re.findall(r"^\s*(\w+)\s+\w+", block, re.M))


@pytest.mark.parametrize("function_name", RATE_FUNCTIONS)
def test_every_column_pitching_rates_reads_is_returned(function_name: str) -> None:
    returned = returns_table_columns(function_name)
    missing = sorted(set(REQUIRED_COLUMNS) - returned)
    assert not missing, (
        f"{function_name} does not return {missing}, which pitching_rates reads. "
        "Add it to the RETURNS TABLE and the SELECT."
    )


def test_the_batting_read_returns_what_its_own_consumer_needs() -> None:
    returned = returns_table_columns("fn_team_batting_form")
    assert {"batting_team", "game_date", "opp_hand", "plate_appearances", "xwoba_sum"} <= returned


def test_the_parser_actually_finds_columns() -> None:
    """Guards the guard: a regex that silently matched nothing would make every
    assertion above vacuously true."""
    assert len(returns_table_columns("fn_pitcher_game_form")) >= 15
