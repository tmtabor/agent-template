"""Pass/fail eval examples using pydantic_evals.

These evals test for specific, verifiable outputs.
Run with: uv run pytest -m eval
"""

from dataclasses import dataclass

import pytest
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from agent.agents import run_agent


@pytest.mark.eval
async def test_agent_returns_output():
    """Basic smoke test: agent runs without error and returns output."""
    output = await run_agent("Say hello.")
    assert output is not None
    assert output.result  # non-empty result


@pytest.mark.eval
async def test_agent_handles_empty_ish_input():
    """Agent should handle minimal input gracefully."""
    output = await run_agent("Hi.")
    assert output is not None


# --- Dataset eval driven by evals/fixtures/example.json ---


@dataclass
class ContainsExpected(Evaluator[str, str]):
    """Pass if the expected output appears in the answer (case-insensitive).

    Cases without an expected_output just need a non-empty answer.
    """

    def evaluate(self, ctx: EvaluatorContext[str, str]) -> bool:
        if ctx.expected_output is None:
            return bool(ctx.output and ctx.output.strip())
        return ctx.expected_output.lower() in ctx.output.lower()


@pytest.mark.eval
async def test_fixture_dataset(example_fixtures: list[dict]):
    """Run every case in evals/fixtures/example.json through the agent.

    Add cases to that JSON file to grow this eval — no code changes needed
    unless a case requires a new kind of check, in which case add an
    Evaluator like ContainsExpected above.
    """
    dataset = Dataset(
        cases=[
            Case(
                name=fixture["name"],
                inputs=fixture["inputs"]["user_input"],
                expected_output=fixture.get("expected_output"),
                metadata=fixture.get("metadata"),
            )
            for fixture in example_fixtures
        ],
        evaluators=[ContainsExpected()],
    )

    async def task(user_input: str) -> str:
        output = await run_agent(user_input)
        return output.result

    report = await dataset.evaluate(task)
    report.print(include_input=True, include_output=True)

    averages = report.averages()
    assert averages is not None
    assert averages.assertions == 1.0, "One or more eval cases failed — see the report above."
