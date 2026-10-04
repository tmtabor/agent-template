"""Smoke tests: every agent stub constructs and runs under TestModel.

Each case imports its stub lazily and skips if the file was deleted by
scripts/choose_pattern.py, so this file never needs editing when a pattern
is chosen. The autouse fixture in conftest.py overrides every Agent under
agent.agents with a TestModel that calls no tools, nested worker agents
included. SMOKE_TOOLS below is where a stub's smoke test opts in to a tool —
the supervisor's delegation tool, so it still really runs its worker here.
"""

import importlib
from decimal import Decimal

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

# Tools a stub's smoke test opts in to calling. The conftest safety net calls no
# tools by default; the supervisor's delegation tool is safe to run (its worker
# is overridden too) and is the point of that pattern, so it stays exercised.
SMOKE_TOOLS = {"agent.agents.supervisor": ["delegate_to_worker_a"]}

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

    model = TestModel(call_tools=SMOKE_TOOLS.get(module_path, []))
    with main_agent.override(model=model):
        result = await main_agent.run("Smoke test input", deps=deps)
    assert result.output is not None

    # Opted-in tools must really have been called, or the opt-in is silently dead.
    called = {
        part.tool_name
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }
    assert set(SMOKE_TOOLS.get(module_path, [])) <= called


@pytest.mark.parametrize(("module_path", "agent_attr", "deps_attr"), STUBS)
async def test_stub_cost_limit_is_enforced(module_path: str, agent_attr: str, deps_attr: str):
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        pytest.skip(f"{module_path} stub was removed by choose_pattern.py")

    assert module.USAGE_LIMITS.cost_limit == Decimal("0.50")

    # TestModel can't be priced, so seed a usage already over the cap.
    main_agent = getattr(module, agent_attr)
    deps = getattr(module, deps_attr)()
    with pytest.raises(UsageLimitExceeded, match="cost_limit"):
        await main_agent.run(
            "Smoke test input",
            deps=deps,
            usage=RunUsage(cost=Decimal("1")),
            usage_limits=module.USAGE_LIMITS,
        )
