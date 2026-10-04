"""configure_logging wires service identity and the content toggle into Logfire."""

import logfire
import pytest

from agent import logging as agent_logging
from agent.config import settings


@pytest.fixture
def calls(monkeypatch) -> dict:
    captured: dict = {}
    monkeypatch.setattr(logfire, "configure", lambda **kw: captured.setdefault("configure", kw))
    monkeypatch.setattr(
        logfire, "instrument_pydantic_ai", lambda **kw: captured.setdefault("instrument", kw)
    )
    # Don't leave a Logfire handler installed on the root logger.
    monkeypatch.setattr(agent_logging.logging, "basicConfig", lambda **kw: None)
    return captured


@pytest.mark.parametrize("token", [None, "test-token"])
def test_service_name_and_environment_reach_logfire(monkeypatch, calls, token):
    monkeypatch.setattr(settings, "logfire_token", token)
    monkeypatch.setattr(settings, "service_name", "my-agent")
    monkeypatch.setattr(settings, "environment", "staging")

    agent_logging.configure_logging()

    assert calls["configure"]["service_name"] == "my-agent"
    assert calls["configure"]["environment"] == "staging"
    assert ("token" in calls["configure"]) == (token is not None)


def test_content_follows_setting_but_explicit_argument_wins(monkeypatch, calls):
    monkeypatch.setattr(settings, "log_content", False)

    agent_logging.configure_logging()
    assert calls["instrument"] == {"include_content": False}

    calls.clear()
    agent_logging.configure_logging(include_content=True)
    assert calls["instrument"] == {"include_content": True}
