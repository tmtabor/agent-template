"""Example unit tests using TestModel — no API calls, no cost.

TestModel simulates agent behavior for fast, deterministic unit tests.
Import it from: from pydantic_ai.models.test import TestModel
"""

from pydantic_ai.models.test import TestModel

from agent.agents import AgentDeps, agent


async def test_agent_runs_with_test_model():
    """Agent runs without error using TestModel (no API call)."""
    with agent.override(model=TestModel()):
        result = await agent.run("Test input", deps=AgentDeps())
    # TestModel returns a placeholder output that satisfies the output_type schema
    assert result.output is not None


async def test_agent_accepts_string_input():
    """Agent accepts a string user prompt."""
    with agent.override(model=TestModel()):
        result = await agent.run("Hello", deps=AgentDeps())
    assert result is not None


async def test_agent_message_history():
    """Demonstrate multi-turn conversation history pattern."""
    with agent.override(model=TestModel()):
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
