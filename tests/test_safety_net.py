"""The unit-test safety net never runs tools unless a test opts in.

tests/conftest.py overrides every agent's model (this file uses the blank example, which
stays in the repo even after `add_agent.py --prune`) with a TestModel. A plain
TestModel() calls *every* tool with junk arguments, which fails for any tool
that validates its input (ModelRetry on "a") and really executes tools with
side effects. The safety net therefore uses call_tools=[]; a test that wants a
tool executed opts in with its own TestModel(call_tools=[...]).
"""

from pydantic_ai import ModelRetry
from pydantic_ai.models.test import TestModel

from examples.blank.agent import BlankDeps, blank_agent as agent


async def test_tools_are_not_called_by_default():
    calls: list[str] = []

    def validating_tool_with_side_effect(query: str) -> str:
        calls.append(query)
        raise ModelRetry("digits only")

    # No model override here: this runs on the autouse fixture's TestModel.
    with agent.override(tools=[validating_tool_with_side_effect]):
        result = await agent.run("hello", deps=BlankDeps())

    assert result.output is not None
    assert calls == []


async def test_a_test_can_opt_in_to_calling_a_tool():
    calls: list[str] = []

    def lookup(query: str) -> str:
        calls.append(query)
        return "found"

    with agent.override(tools=[lookup], model=TestModel(call_tools=["lookup"])):
        await agent.run("hello", deps=BlankDeps())

    assert len(calls) == 1


def test_agents_held_in_containers_are_found():
    """The net finds an Agent that a module only holds inside a dict, list or tuple."""
    from pydantic_ai import Agent

    from tests.conftest import _agents_in

    held = Agent(TestModel())
    assert _agents_in(held) == [held]
    assert _agents_in({"a": held, "b": 1}) == [held]
    assert _agents_in([held, "x"]) == [held]
    assert _agents_in((held,)) == [held]
    assert _agents_in("not an agent") == []
    assert _agents_in({"a": 1}) == []
