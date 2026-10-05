"""Shared helpers for tests that run every example in place."""

import importlib
import sys
from pathlib import Path

import pytest

# scripts/ is not a package; make its modules importable (also done via pytest's
# `pythonpath` setting, kept here so the helpers work when imported standalone).
SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from example_manifest import Example, discover  # noqa: E402

EXAMPLES = discover()


def example_ids() -> list[pytest.param]:
    return [pytest.param(e, id=e.name) for e in EXAMPLES]


def import_example(example: Example):
    """Import the example's module in place, skipping if its extra dependencies are absent."""
    try:
        return importlib.import_module(example.module)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".")[0] in {"examples", "agent"}:
            raise
        pytest.skip(f"{example.name} needs {exc.name!r} (run it in its own environment)")
