"""CLAUDE.md rule 3 / model doc A1, §10.5: market odds are never a model input.

`builder.py` asserts this in a comment ("by construction, not by filter").
This makes it enforceable. The failure mode it guards is not someone adding
an `odds` column on purpose — it's a well-meant `from sbm.odds import ...`
inside a feature module to reuse a helper, which quietly collapses the model
toward the market and makes every CLV number meaningless.

Structural, like `tests/test_architecture.py`: it fails the build, not a
review. Scoped to the feature package because that is `ingest`'s to keep
clean; the sport-agnostic equivalent lives in the architecture test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

FEATURES = Path(__file__).resolve().parents[3] / "src" / "sbm" / "sports" / "mlb" / "features"

FORBIDDEN_MODULES = ("sbm.odds",)
FORBIDDEN_NAMES = (
    "price_american",
    "implied_prob",
    "market_fair_prob",
    "market_odds",
    "line_snapshots",
    "devig",
)


def _feature_modules() -> list[Path]:
    return sorted(FEATURES.rglob("*.py"))


def test_there_are_feature_modules_to_check() -> None:
    """Guards against the whole suite silently passing on an empty glob."""
    assert _feature_modules()


@pytest.mark.parametrize("path", _feature_modules(), ids=lambda p: p.name)
def test_feature_module_never_imports_the_odds_layer(path: Path) -> None:
    tree = ast.parse(path.read_text(), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)

    leaked = {
        name
        for name in imported
        for forbidden in FORBIDDEN_MODULES
        if name == forbidden or name.startswith(f"{forbidden}.")
    }
    assert not leaked, (
        f"{path.name} imports the odds layer {sorted(leaked)} — market odds are "
        "never a model input (model doc A1); they belong only to edge/CLV"
    )


@pytest.mark.parametrize("path", _feature_modules(), ids=lambda p: p.name)
def test_feature_module_defines_no_price_bearing_identifier(path: Path) -> None:
    """Catches a hand-rolled odds column that never imports `sbm.odds`.

    Only binding occurrences count — assignments, parameters, attributes —
    so the modules may still *discuss* market odds in prose, which several
    deliberately do to explain why they exclude them.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Attribute):
            bound.add(node.attr)

    offenders = {
        name for name in bound for forbidden in FORBIDDEN_NAMES if forbidden in name.lower()
    }
    assert not offenders, (
        f"{path.name} binds price-bearing name(s) {sorted(offenders)} — model doc "
        "§10.5 cuts 'market odds as any model input'"
    )
