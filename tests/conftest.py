"""Pytest fixtures for unit tests."""

import os

# Unit tests must run with no real credentials and no API calls. Settings
# requires a provider key for the selected model at import time, and the
# module-level Agent construction may create a provider client that also
# wants a key — set dummy values before anything under agent/ is imported.
# setdefault() leaves real keys untouched if they are present.
os.environ.setdefault("ANTHROPIC_API_KEY", "unit-test-dummy-key")
os.environ.setdefault("OPENAI_API_KEY", "unit-test-dummy-key")

import pytest  # noqa: E402

from agent.logging import configure_logging  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Configure logging once for the test session."""
    configure_logging()
