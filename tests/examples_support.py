"""Shared helpers for tests that run every example in place."""

import importlib
import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import ModuleType

import pytest
from pydantic_ai.models.test import TestModel

# scripts/ is not a package; make its modules importable (also done via pytest's
# `pythonpath` setting, kept here so the helpers work when imported standalone).
SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from example_manifest import Example, discover  # noqa: E402

EXAMPLES = discover()


def example_ids() -> list[pytest.param]:
    return [pytest.param(e, id=e.name) for e in EXAMPLES]


def is_labeled(label: str | None, example_name: str) -> bool:
    """Trace labels are the agent's name, or `<name>.<role>` for helpers in the same example."""
    return label == example_name or (label or "").startswith(f"{example_name}.")


def import_example(example: Example) -> ModuleType:
    """Import the example's module in place, skipping if its extra dependencies are absent."""
    try:
        return importlib.import_module(example.module)
    except ImportError as exc:
        # A package the example declares in `dependencies` is missing from this environment (it
        # runs in its own isolated one). An import failure in the repo's own code is a real error,
        # and so is any failure in an example that declares no dependencies.
        name = (getattr(exc, "name", None) or "").split(".")[0]
        if example.dependencies and name not in {"examples", "agent"}:
            pytest.skip(f"{example.name} needs its declared dependencies: {exc}")
        raise


@contextmanager
def smoke_overrides(example: Example, module: ModuleType) -> Iterator[None]:
    """Apply the manifest's `[smoke.<agent>]` TestModels, so the whole flow can run offline.

    Agents without an entry keep the safety net's default (a TestModel that calls no tools).
    """
    with ExitStack() as stack:
        for variable, config in example.smoke.items():
            kwargs: dict = {"call_tools": list(config.call_tools)}
            if config.output is not None:
                kwargs["custom_output_args"] = config.output
            stack.enter_context(getattr(module, variable).override(model=TestModel(**kwargs)))
        yield
