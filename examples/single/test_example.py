"""Example unit tests using TestModel — no API calls, no cost.

This file stays with the `single` example (add_agent.py does not copy it); it is a
recipe for testing your own agent.

TestModel simulates agent behavior for fast, deterministic unit tests.
Import it from: from pydantic_ai.models.test import TestModel

Use TestModel(call_tools=[]) for agent-level tests: a default TestModel() calls every
tool with junk arguments, which breaks tools that validate input. See
tests/test_safety_net.py for opting in to a tool call.
"""

from pydantic_ai.models.test import TestModel

from agent.runs import RunResult
from examples.single.agent import AgentDeps, agent, run_agent


async def test_agent_runs_with_test_model():
    """Agent runs without error using TestModel (no API call)."""
    with agent.override(model=TestModel(call_tools=[])):
        result = await agent.run("Test input", deps=AgentDeps())
    # TestModel returns a placeholder output that satisfies the output_type schema
    assert result.output is not None


async def test_agent_accepts_string_input():
    """Agent accepts a string user prompt."""
    with agent.override(model=TestModel(call_tools=[])):
        result = await agent.run("Hello", deps=AgentDeps())
    assert result is not None


async def test_agent_message_history():
    """Demonstrate multi-turn conversation history pattern."""
    with agent.override(model=TestModel(call_tools=[])):
        result1 = await agent.run("First message", deps=AgentDeps())
        history = result1.all_messages()  # all_messages(), not new_messages() — keeps all turns

        result2 = await agent.run(
            "Follow-up message",
            deps=AgentDeps(),
            message_history=history,
        )

    assert result2.output is not None
    # History from both turns is available
    assert len(result2.all_messages()) > len(result1.all_messages())


async def test_run_agent_returns_a_run_result():
    """run_agent wraps the native result: `.output`, total `.usage`, and the single step."""
    with agent.override(model=TestModel(call_tools=[])):
        result = await run_agent("Test input")

    assert isinstance(result, RunResult)
    assert result.output is not None
    assert [step.agent for step in result.steps] == ["single"]
    assert result.steps[0].result.output == result.output  # the native result, untouched
    assert result.usage.requests == 1
