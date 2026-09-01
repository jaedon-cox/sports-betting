"""Jobs B and H must stay httpx-only — this is a minutes-budget guard.

Backend doc §2.2 bills whole minutes per *invocation*, so the cost driver is
trigger frequency, not runtime. Job B fires ~14x/day and Job H must keep working
when every upstream source is dark; both workflows therefore `pip install httpx`
and set `PYTHONPATH=src` instead of doing an editable install of the scientific
stack. An innocuous new import in a shared module (`config.py` imported
`sbm.core.pricing` once, whose package `__init__` pulls scipy through `devig`)
silently makes ~420 invocations a month install numpy/pandas/scipy/sklearn for
nothing. That is invisible in review and expensive in production, so it is a
test.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src"
SCIENTIFIC_STACK = {"numpy", "pandas", "scipy", "sklearn"}

LIGHT_JOBS = {
    "b": "sbm.jobs.job_b_intraday",
    "h": "sbm.jobs.job_h_heartbeat",
}


def _module_path(name: str) -> Path | None:
    module = SRC / (name.replace(".", "/") + ".py")
    if module.exists():
        return module
    package = SRC / name.replace(".", "/") / "__init__.py"
    return package if package.exists() else None


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def third_party_closure(root: str) -> set[str]:
    """Every non-stdlib top-level package `root` transitively imports.

    Parent packages count: `from sbm.core.pricing.kelly import X` executes
    `sbm/core/pricing/__init__.py`, which is exactly how scipy got in.
    """
    seen: set[str] = set()
    stack = [root]
    third_party: set[str] = set()
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        path = _module_path(module)
        if path is None:
            continue
        for name in _imports(path):
            top = name.split(".")[0]
            if top == "sbm":
                stack.append(name)
                stack.append(name.rsplit(".", 1)[0])
            elif top not in sys.stdlib_module_names:
                third_party.add(top)
    return third_party


@pytest.mark.parametrize("letter,module", sorted(LIGHT_JOBS.items()))
def test_high_frequency_jobs_need_nothing_but_httpx(letter: str, module: str) -> None:
    needed = third_party_closure(module) | third_party_closure("sbm.jobs.runner")
    leaked = needed & SCIENTIFIC_STACK
    assert not leaked, (
        f"job {letter} ({module}) now transitively imports {sorted(leaked)}. "
        f".github/workflows/job-{'b-intraday' if letter == 'b' else 'h-heartbeat'}.yml "
        "installs httpx only — either drop the import or change the workflow and "
        "the minute budget in .github/workflows/README.md."
    )
    assert needed <= {"httpx"}, f"job {letter} gained a new dependency: {sorted(needed - {'httpx'})}"
