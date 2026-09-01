"""Structural guards over db/. These fail the build, not a code review.

No Supabase project has ever been provisioned, so none of this SQL has
been executed — every one of these invariants is otherwise checked by
nobody. They are deliberately textual and cheap; they catch the class of
mistake that would surface as a 404 or a silently stale number against a
real database, not as a syntax error.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DB = Path(__file__).resolve().parents[3] / "db"
SQL_FILES = sorted(DB.rglob("*.sql"))

_CREATE_MATVIEW = re.compile(r"CREATE\s+MATERIALIZED\s+VIEW\s+(\w+)", re.IGNORECASE)
_CREATE_RELATION = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
    re.IGNORECASE,
)
_UNIQUE_INDEX = re.compile(r"CREATE\s+UNIQUE\s+INDEX\s+\w+\s+ON\s+(\w+)", re.IGNORECASE)
_GRANT_ON_RELATIONS = re.compile(
    r"GRANT\s+(?!USAGE\b|EXECUTE\b)[\w\s,]+?\s+ON\s+(.+?)\s+TO\s", re.IGNORECASE | re.DOTALL
)
_POLICY_TARGET = re.compile(r"CREATE\s+POLICY\s+\w+\s+ON\s+(\w+)", re.IGNORECASE)
_RLS_TARGET = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", re.IGNORECASE
)


def _code(path: Path) -> str:
    """File text with `--` comments removed.

    Every check below is about what the SQL *does*. These files carry more
    prose than code by design (the reasoning is the point), and matching a
    relation name inside an explanation is a false positive every time.
    """
    return "\n".join(re.sub(r"--.*$", "", line) for line in path.read_text().splitlines())


def _all_code() -> str:
    return "\n".join(_code(p) for p in SQL_FILES)


def _created(pattern: re.Pattern[str]) -> set[str]:
    return {m.group(1) for p in SQL_FILES for m in pattern.finditer(_code(p))}


def test_every_matview_is_in_fn_refresh_rollups() -> None:
    """A matview nobody refreshes serves its build-time snapshot forever
    with nothing failing — the worst failure mode in this schema, because
    the numbers stay plausible. 011_rollup_refresh.sql says to add the
    next one; this is what makes that instruction binding."""
    body = _code(DB / "migrations" / "011_rollup_refresh.sql")
    refreshed = set(re.findall(r"REFRESH\s+MATERIALIZED\s+VIEW\s+(\w+)", body, re.IGNORECASE))
    assert _created(_CREATE_MATVIEW) == refreshed


def test_every_matview_has_a_unique_index() -> None:
    """§3.3: REFRESH ... CONCURRENTLY needs one, and it is also what makes
    the declared grain actually hold."""
    indexed = _created(_UNIQUE_INDEX)
    assert _created(_CREATE_MATVIEW) <= indexed


def test_no_rls_or_policy_targets_a_matview() -> None:
    """Postgres has no RLS on materialized views at all — either statement
    is a hard error at apply time, and the whole file after it never
    runs."""
    matviews = _created(_CREATE_MATVIEW)
    assert not (_created(_POLICY_TARGET) & matviews)
    assert not (_created(_RLS_TARGET) & matviews)


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_grants_name_relations_that_exist(path: Path) -> None:
    """A typo'd GRANT is indistinguishable from a missing one when a read
    fails, and it is the first thing suspected when a relation looks
    unreachable through PostgREST."""
    relations = _created(_CREATE_RELATION)
    for match in _GRANT_ON_RELATIONS.finditer(_code(path)):
        for name in (n.strip() for n in match.group(1).split(",")):
            assert name in relations, f"{path.name} GRANTs on unknown relation {name!r}"


def test_the_live_clv_column_is_named_for_its_units() -> None:
    """`clv_pct_live` was an ABSOLUTE probability difference sharing a
    name-shape with the RELATIVE pick_settlements.clv_pct — ~2x apart at
    typical prices. The rename is only worth anything if the old name is
    gone everywhere."""
    assert "clv_pct_live" not in _all_code()
    assert "clv_abs_live" in _code(DB / "views" / "v_pick_clv_live.sql")


def test_no_dollar_amount_is_persisted() -> None:
    """§3.5/§5: kelly_stake_fraction (a %) is the only stake figure in the
    schema. bankroll_usd may survive only in the two migrations that
    record its life — 006 created it, 010 dropped it."""
    offenders = [p.name for p in SQL_FILES if "bankroll_usd" in _code(p)]
    assert offenders == ["006_users_and_auth.sql", "010_drop_bankroll_usd.sql"]


_SRC = Path(__file__).resolve().parents[3] / "src" / "sbm"
_RPC_CALL = re.compile(r"\brpc\(\s*\"(\w+)\"")


def test_every_rpc_python_calls_is_defined_in_db() -> None:
    """Nothing else connects the two halves of an RPC contract.

    `store/` and `jobs/` reach Postgres only through named functions, and a
    call to one `db/` never shipped is invisible until the job runs against a
    real project and gets a 404 — which, with no project provisioned, means
    nobody finds out at all. If this fails on a function you just started
    calling, the fix is a migration in db/, not a change here.
    """
    called = {
        m.group(1)
        for path in _SRC.rglob("*.py")
        for m in _RPC_CALL.finditer(path.read_text())
    }
    defined = _created(re.compile(r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+(\w+)", re.IGNORECASE))
    assert called, "the RPC-call regex matched nothing — it has drifted from the call sites"
    assert called <= defined, f"called but not defined in db/: {sorted(called - defined)}"


_CONSTRAINT_KEYWORDS = {"CHECK", "UNIQUE", "PRIMARY", "FOREIGN", "CONSTRAINT", "EXCLUDE"}
_SERVER_ASSIGNED = {"id", "created_at"}


def _table_columns(name: str) -> set[str]:
    """Column names declared in `CREATE TABLE <name> (...)`."""
    body = re.search(
        rf"CREATE\s+TABLE\s+{name}\s*\((.*?)\n\);", _all_code(), re.IGNORECASE | re.DOTALL
    )
    assert body, f"no CREATE TABLE {name} found"
    return {
        m.group(1)
        for line in body.group(1).splitlines()
        if (m := re.match(r"\s+(\w+)\s+\S", line))
        and m.group(1).upper() not in _CONSTRAINT_KEYWORDS
    }


def test_publish_run_writes_every_picks_column() -> None:
    """fn_publish_run is the ONLY writer of picks (§2.4 atomic publish), so a
    column it omits is a column that can never be set.

    This is the general form of a bug that shipped: 003 added
    picks.devig_method under `CHECK ((market_fair_prob IS NULL) = (devig_method
    IS NULL))` and 007's INSERT list never included it, so every priced pick
    violated the CHECK and rolled back the whole slate. Nothing caught it
    because nothing executes this SQL.
    """
    latest = max(p for p in SQL_FILES if "CREATE OR REPLACE FUNCTION fn_publish_run" in _code(p))
    insert = re.search(r"INSERT\s+INTO\s+picks\s*\((.*?)\)", _code(latest), re.DOTALL)
    assert insert, f"{latest.name} defines fn_publish_run but no INSERT INTO picks"
    written = {c.strip() for c in insert.group(1).split(",")}
    assert written == _table_columns("picks") - _SERVER_ASSIGNED


_MANIFEST = DB / "APPLY_ORDER.md"

# Dependency edges that are NOT derivable from the filenames or from the
# object graph, so a reader ordering db/views/ by inspection gets them wrong.
# This is the alphabetical-order bug encoded: mv_clv_trend/mv_roi_curve select
# from record_summary, and record_breakdown reads fn_american_payout_multiplier
# which is defined inside record_summary.sql rather than in a migration.
_MUST_PRECEDE = [
    ("db/views/record_summary.sql", "db/views/mv_clv_trend.sql"),
    ("db/views/record_summary.sql", "db/views/mv_roi_curve.sql"),
    ("db/views/record_summary.sql", "db/views/record_breakdown.sql"),
]


def _manifest_order() -> list[str]:
    """Paths from the first fenced block in APPLY_ORDER.md, in order.

    Parsed from the fence rather than the whole file so prose naming a file
    cannot silently become a manifest entry.
    """
    fence = re.search(r"```text\n(.*?)```", _MANIFEST.read_text(), re.DOTALL)
    assert fence, "APPLY_ORDER.md has no ```text manifest block"
    return [
        line.split("#")[0].strip()
        for line in fence.group(1).splitlines()
        if line.split("#")[0].strip()
    ]


def test_manifest_names_every_sql_file_exactly_once() -> None:
    """A manifest nobody maintains reproduces the bug it exists to prevent.

    db/views/ cannot be applied alphabetically — record_summary.sql sorts after
    the three files that depend on it — so the order lives only in
    APPLY_ORDER.md. Add a file without listing it and this fails.
    """
    listed = _manifest_order()
    assert len(listed) == len(set(listed)), "APPLY_ORDER.md lists a file twice"
    on_disk = {str(p.relative_to(DB.parent)) for p in SQL_FILES}
    assert set(listed) == on_disk, (
        f"unlisted on disk: {sorted(on_disk - set(listed))}; "
        f"listed but missing: {sorted(set(listed) - on_disk)}"
    )


def test_manifest_respects_the_dependency_edges() -> None:
    """Membership is not enough — the order is the whole point."""
    listed = _manifest_order()
    position = {path: i for i, path in enumerate(listed)}
    for earlier, later in _MUST_PRECEDE:
        assert position[earlier] < position[later], (
            f"{earlier} must be applied before {later}"
        )
    # Phase order: policies/001 does REVOKE ALL ON ALL TABLES, which only
    # covers the views and matviews if they already exist.
    phase = {"migrations": 0, "views": 1, "policies": 2}
    phases = [phase[p.split("/")[1]] for p in listed]
    assert phases == sorted(phases), "manifest interleaves migrations/, views/ and policies/"
