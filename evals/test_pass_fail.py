"""Pass/fail eval examples using pydantic_evals.

These evals test for specific, verifiable outputs.
Run with: uv run pytest -m eval
"""

import pytest

from agent.agents.single import run_agent


@pytest.mark.eval
@pytest.mark.asyncio
async def test_agent_returns_output():
    """Basic smoke test: agent runs without error and returns output."""
    output = await run_agent("Say hello.")
    assert output is not None
    assert output.result  # non-empty result


@pytest.mark.eval
@pytest.mark.asyncio
async def test_agent_handles_empty_ish_input():
    """Agent should handle minimal input gracefully."""
    output = await run_agent("Hi.")
    assert output is not None


@pytest.mark.eval
@pytest.mark.asyncio
async def test_agent_confidence_in_range():
    """Agent output confidence should be between 0 and 1."""
    output = await run_agent("What is 2 + 2?")
    assert 0.0 <= output.confidence <= 1.0


# --- pydantic_evals Dataset pattern ---
# For more structured evals with datasets, use this pattern:
#
# from pydantic_evals import Dataset, Case
#
# dataset = Dataset(cases=[
#     Case(name="greeting", inputs={"user_input": "Hello!"}, expected_output=...),
#     Case(name="math", inputs={"user_input": "What is 2+2?"}, expected_output=...),
# ])
#
# @pytest.mark.eval
# async def test_dataset():
#     report = await dataset.evaluate(lambda inputs: run_agent(inputs["user_input"]))
#     report.print(include_input=True, include_output=True, include_scores=True)
#     assert report.averages().total_score >= 0.8
