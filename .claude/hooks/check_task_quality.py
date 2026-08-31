#!/usr/bin/env python3
"""TaskCompleted gate: block a task that leaves the tree unbuildable or bloated.

Exit 2 sends stderr back to the teammate as feedback and prevents completion,
so oversized modules get split by whoever wrote them rather than piling up.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SOFT_CAP = 150
HARD_CAP = 250


def oversized(root: Path) -> list[tuple[Path, int]]:
    hits = []
    for path in (root / "src").rglob("*.py"):
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > HARD_CAP:
            hits.append((path.relative_to(root), lines))
    return sorted(hits, key=lambda item: -item[1])


def duplicate_test_basenames(root: Path) -> list[str]:
    """Two test files sharing a basename break pytest COLLECTION, not one test.

    Under the default "prepend" import mode they collide as the same top-level
    module, which aborts the entire run — so this cannot be caught by a test,
    and has to be checked before pytest is invoked.
    """
    seen: dict[str, list[Path]] = {}
    for path in (root / "tests").rglob("test_*.py"):
        seen.setdefault(path.name, []).append(path.relative_to(root))
    return [
        f"{name} exists in {len(paths)} places ({', '.join(str(p) for p in sorted(paths))})"
        f" — same-named test files collide at collection; rename one"
        for name, paths in sorted(seen.items())
        if len(paths) > 1
    ]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    root = Path(payload.get("cwd") or ".").resolve()
    if not (root / "src").is_dir():
        return 0

    problems = []
    for clash in duplicate_test_basenames(root):
        problems.append(f"  {clash}")
    for path, lines in oversized(root):
        problems.append(f"  {path} is {lines} lines (hard cap {HARD_CAP}) — split it into a package")

    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-x"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if tests.returncode != 0:
        tail = "\n".join(tests.stdout.strip().splitlines()[-15:])
        problems.append(f"  pytest is failing:\n{tail}")

    if not problems:
        return 0
    task = payload.get("task_name", "this task")
    print(
        f"Cannot complete '{task}' — fix these first (target {SOFT_CAP} lines/module):\n"
        + "\n".join(problems),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
