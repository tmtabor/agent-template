"""Smoke tests: every agent stub constructs and runs under TestModel.

Each case imports its stub lazily and skips if the file was deleted by
scripts/choose_pattern.py, so this file never needs editing when a pattern
is chosen. The autouse fixture in conftest.py overrides every Agent under
agent.agents with TestModel — nested worker agents included, so the
supervisor's delegation tool really runs its worker here.
"""

import importlib

import pytest

STUBS = [
    ("agent.agents.single", "agent", "AgentDeps"),
    ("agent.agents.supervisor", "supervisor_agent", "SharedDeps"),
    ("agent.agents.tool_calling", "tool_agent", "ToolAgentDeps"),
]


@pytest.mark.parametrize(("module_path", "agent_attr", "deps_attr"), STUBS)
async def test_stub_runs_with_test_model(module_path: str, agent_attr: str, deps_attr: str):
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        pytest.skip(f"{module_path} stub was removed by choose_pattern.py")

    main_agent = getattr(module, agent_attr)
    deps = getattr(module, deps_attr)()

    result = await main_agent.run("Smoke test input", deps=deps)
    assert result.output is not None
