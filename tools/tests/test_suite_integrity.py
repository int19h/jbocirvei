"""Checks of the test suite itself. They find failures that look like successes.

Two such failures happened here before. A skip guard used the real archive as
its default. So it never skipped where it mattered, and no test proved that the
guarded module skipped at all. One module defined a test function two times. So
Python kept the second, and the first never ran, but `pytest -q` reported the
file as passed. Neither failure showed in the place people look: the pass count.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def module_paths() -> list[Path]:
    return sorted(TESTS.glob("test_*.py"))


def test_no_test_module_defines_a_name_twice() -> None:
    """A shadowed definition is a test that stops running, and nothing reports it."""

    duplicates: list[str] = []
    for path in module_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = Counter(
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        )
        duplicates.extend(
            f"{path.name}:{name} defined {count} times"
            for name, count in sorted(names.items())
            if count > 1
        )
    assert not duplicates, "; ".join(duplicates)


def test_every_module_has_at_least_one_test() -> None:
    """If all tests of a module lose the `test_` prefix, the module still passes."""

    empty = [
        path.name
        for path in module_paths()
        if not any(
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name.startswith("test_")
            for node in ast.parse(path.read_text(encoding="utf-8")).body
        )
    ]
    assert not empty, f"test modules with no tests: {', '.join(empty)}"
