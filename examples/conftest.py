"""Fixtures for tests that live inside examples/.

Settings validates the provider key at import time, and tests/conftest.py (which sets dummy
keys for the unit tests) is not loaded when you run just `pytest examples/<name>`. A dummy key
spends nothing: these tests override the model, and a call that escaped would fail to
authenticate rather than bill. (A real key already in the environment is left alone, which is
how the `eval`-marked live tests reach the real model.)
"""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "unit-test-dummy-key")
os.environ.setdefault("OPENAI_API_KEY", "unit-test-dummy-key")

import pytest  # noqa: E402

from agent.logging import configure_logging  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """The live tests read agent and tool calls from spans (evals/trace.py), which need Logfire."""
    configure_logging(include_content=True)
