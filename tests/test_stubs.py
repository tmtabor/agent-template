"""Smoke tests: every agent stub constructs and runs under TestModel.

Each case imports its stub lazily and skips if the file was deleted by
scripts/choose_pattern.py, so this file never needs editing when a pattern
is chosen. All Agent instances in the module are overridden with TestModel —
this covers nested agents too (TestModel calls every tool, so the
supervisor's delegation tool really runs the worker agent).
"""

import importlib
from contextlib import ExitStack

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

STUBS = [
    ("agent.agents.single", "agent", "AgentDeps"),
    ("agent.agents.supervisor", "supervisor_agent", "SharedDeps"),
    ("agent.agents.tool_calling", "tool_agent", "ToolAgentDeps"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("module_path", "agent_attr", "deps_attr"), STUBS)
async def test_stub_runs_with_test_model(module_path: str, agent_attr: str, deps_attr: str):
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        pytest.skip(f"{module_path} stub was removed by choose_pattern.py")

    main_agent = getattr(module, agent_attr)
    deps = getattr(module, deps_attr)()

    with ExitStack() as stack:
        for value in vars(module).values():
            if isinstance(value, Agent):
                stack.enter_context(value.override(model=TestModel()))
        result = await main_agent.run("Smoke test input", deps=deps)

    assert result.output is not None
