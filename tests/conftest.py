"""Pytest fixtures for unit tests."""

import os

# Unit tests must run with no real credentials and no API calls. Settings
# requires a provider key for the selected model at import time, and the
# module-level Agent construction may create a provider client that also
# wants a key — set dummy values before anything under agent/ is imported.
# setdefault() leaves real keys untouched if they are present.
os.environ.setdefault("ANTHROPIC_API_KEY", "unit-test-dummy-key")
os.environ.setdefault("OPENAI_API_KEY", "unit-test-dummy-key")

import importlib  # noqa: E402
import pkgutil  # noqa: E402
import sys  # noqa: E402
from contextlib import ExitStack  # noqa: E402

import pytest  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402

import agent.agents  # noqa: E402
from agent.logging import configure_logging  # noqa: E402
from tests.agent_finder import agents_in  # noqa: E402

# Module-name prefixes whose Agent instances the safety net overrides: your agents,
# and the examples (which tests run in place).
OVERRIDDEN_PREFIXES = ("agent.agents", "examples.")


def _preimport_agent_modules() -> None:
    """Import every agent module up front so the override also covers lazy imports.

    A module first imported mid-test would escape the net, so import them all here.
    Your agents must import cleanly — an error surfaces rather than being hidden. An
    example whose extra dependencies aren't installed is skipped (it has its own
    isolated test run).
    """
    for module_info in pkgutil.iter_modules(agent.agents.__path__):
        importlib.import_module(f"agent.agents.{module_info.name}")
    try:
        import examples
    except ModuleNotFoundError:  # pruned
        return
    for module_info in pkgutil.iter_modules(examples.__path__):
        if not module_info.ispkg:  # examples/conftest.py is not an example
            continue
        try:
            importlib.import_module(f"examples.{module_info.name}.agent")
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.split(".")[0] in {"examples", "agent"}:
                raise
            # A third-party dependency this example declares but the root env lacks.


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Configure logging once for the test session."""
    configure_logging()


@pytest.fixture(autouse=True)
def override_all_agents_with_test_model():
    """Safety net: no unit test may ever hit a real model API.

    Overrides every Agent defined under agent.agents and examples — including
    nested worker agents that tools delegate to — with TestModel. Tests can still
    apply their own override on top; the innermost override wins.

    The TestModel uses call_tools=[]: a default TestModel() calls *every* tool
    with junk arguments ("a"), which fails any tool that validates its input
    (ModelRetry) and really executes tools that write, send or bill. Same rule
    as for models: nothing runs for real unless a test asks. Test tool logic by
    calling the tool function directly (tests/test_tools.py), and opt in to an
    end-to-end tool call with TestModel(call_tools=["tool_name"]) in the test.

    Agent modules are pre-imported (see _preimport_agent_modules) so the override
    also covers modules a test imports lazily in its body.
    """
    _preimport_agent_modules()

    with ExitStack() as stack:
        seen: set[int] = set()  # an Agent reachable twice (variable and dict) is overridden once
        for name, module in list(sys.modules.items()):
            if name.startswith(OVERRIDDEN_PREFIXES) and module is not None:
                for value in vars(module).values():
                    for found in agents_in(value):
                        if id(found) not in seen:
                            seen.add(id(found))
                            stack.enter_context(found.override(model=TestModel(call_tools=[])))
        yield
