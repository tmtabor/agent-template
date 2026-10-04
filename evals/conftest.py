"""Pytest fixtures for eval runs."""

import json
from pathlib import Path

import pytest

from agent.logging import configure_logging


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Configure logging once for the eval session."""
    # Force content on: span-based evaluators (ArgumentCorrectness) read tool
    # arguments from spans, so AGENT_LOG_CONTENT=false must not break evals.
    configure_logging(include_content=True)


@pytest.fixture
def example_fixtures() -> list[dict]:
    """Load example eval fixtures from JSON."""
    fixtures_path = Path(__file__).parent / "fixtures" / "example.json"
    return json.loads(fixtures_path.read_text())
