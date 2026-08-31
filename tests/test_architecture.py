"""Structural guards. These fail the build, not a code review.

They encode the two rules that keep the codebase scalable to props and to other
sports: the shared engine may not learn about baseball, and no module may grow
past the size where it stops being debuggable.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
SPORT_AGNOSTIC = ("contracts", "core", "markets")
HARD_LINE_CAP = 250


def _modules(*subpackages: str) -> list[Path]:
    return sorted(p for sub in subpackages for p in (SRC / "sbm" / sub).rglob("*.py"))


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", _modules(*SPORT_AGNOSTIC), ids=str)
def test_shared_engine_is_sport_agnostic(path: Path) -> None:
    """contracts/, core/ and markets/ must not import any sport vertical.

    A violation here is how "scalable to other sports" quietly dies.
    """
    leaked = {name for name in _imported_names(path) if name.startswith("sbm.sports")}
    assert not leaked, f"{path.relative_to(SRC)} imports sport-specific code: {sorted(leaked)}"


@pytest.mark.parametrize("path", _modules(""), ids=str)
def test_modules_stay_debuggable(path: Path) -> None:
    """No module past the hard cap. Split it into a package instead."""
    lines = len(path.read_text().splitlines())
    assert lines <= HARD_LINE_CAP, (
        f"{path.relative_to(SRC)} is {lines} lines (cap {HARD_LINE_CAP}) — split it"
    )


def test_contracts_hold_no_logic() -> None:
    """contracts/ is protocols and dataclasses only — no importable behaviour."""
    for path in _modules("contracts"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                pytest.fail(f"{path.name} defines module-level function {node.name}()")
