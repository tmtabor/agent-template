"""Pytest fixtures for unit tests."""

import os

# Unit tests must run with no real credentials and no API calls. Settings
# requires a provider key for the selected model at import time, and the
# module-level Agent construction may create a provider client that also
# wants a key — set dummy values before anything under agent/ is imported.
# setdefault() leaves real keys untouched if they are present.
os.environ.setdefault("ANTHROPIC_API_KEY", "unit-test-dummy-key")
os.environ.setdefault("OPENAI_API_KEY", "unit-test-dummy-key")

import sys  # noqa: E402
from contextlib import ExitStack  # noqa: E402

import pytest  # noqa: E402
from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402

from agent.logging import configure_logging  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Configure logging once for the test session."""
    configure_logging()


@pytest.fixture(autouse=True)
def override_all_agents_with_test_model():
    """Safety net: no unit test may ever hit a real model API.

    Overrides every Agent defined under agent.agents — including nested
    worker agents that tools delegate to — with TestModel. Tests can still
    apply their own override on top; the innermost override wins.
    """
    with ExitStack() as stack:
        for name, module in list(sys.modules.items()):
            if name.startswith("agent.agents") and module is not None:
                for value in vars(module).values():
                    if isinstance(value, Agent):
                        stack.enter_context(value.override(model=TestModel()))
        yield
