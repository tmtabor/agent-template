"""Pass/fail eval examples using pydantic_evals.

These evals test for specific, verifiable outputs.
Run with: uv run pytest -m eval
"""

from dataclasses import dataclass

import pytest
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import (
    ArgumentCorrectness,
    Evaluator,
    EvaluatorContext,
    MaxModelRequests,
    MaxToolCalls,
    ToolCorrectness,
    TrajectoryMatch,
)

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


# Behavioral budgets, applied to every case. These are span-based evaluators:
# they grade how the agent got to its answer, not just the answer, and need
# the Logfire/OpenTelemetry setup in evals/conftest.py to capture spans (without
# spans they fail with a "no span tree" reason). Keep them comfortably below
# the stub's USAGE_LIMITS.request_limit — a run that merely scrapes under the
# hard limit is still a looping run.
MAX_MODEL_REQUESTS = 5
MAX_TOOL_CALLS = 4


def _case_evaluators(fixture: dict) -> list[Evaluator]:
    """Build optional per-case behavioral evaluators from a fixture's keys.

    - expected_tools: ["a", "b"]   -> exactly these tools were called (any order)
    - expected_trajectory: ["a"]   -> tools were called in roughly this order (F1 score)
    - expected_arguments: {"tool": "a", "args": {"q": "x"}} -> tool "a" got these args
    """
    evaluators: list[Evaluator] = []
    if "expected_tools" in fixture:
        evaluators.append(ToolCorrectness(expected_tools=fixture["expected_tools"]))
    if "expected_trajectory" in fixture:
        evaluators.append(TrajectoryMatch(expected_trajectory=fixture["expected_trajectory"]))
    if "expected_arguments" in fixture:
        expected = fixture["expected_arguments"]
        evaluators.append(
            ArgumentCorrectness(tool_name=expected["tool"], expected_arguments=expected["args"])
        )
    return evaluators


@pytest.mark.eval
async def test_fixture_dataset(example_fixtures: list[dict]):
    """Run every case in evals/fixtures/example.json through the agent.

    Add cases to that JSON file to grow this eval — no code changes needed
    unless a case requires a new kind of check, in which case add an
    Evaluator like ContainsExpected above. Tool-using agents can add the
    optional expected_tools / expected_trajectory / expected_arguments keys
    to a fixture (see _case_evaluators).
    """
    dataset = Dataset(
        name="example",
        cases=[
            Case(
                name=fixture["name"],
                inputs=fixture["inputs"]["user_input"],
                expected_output=fixture.get("expected_output"),
                metadata=fixture.get("metadata"),
                evaluators=_case_evaluators(fixture),
            )
            for fixture in example_fixtures
        ],
        evaluators=[
            ContainsExpected(),
            MaxModelRequests(max_requests=MAX_MODEL_REQUESTS),
            MaxToolCalls(max_calls=MAX_TOOL_CALLS),
        ],
    )

    async def task(user_input: str) -> str:
        output = await run_agent(user_input)
        return output.result

    report = await dataset.evaluate(task)
    report.print(include_input=True, include_output=True)

    averages = report.averages()
    assert averages is not None
    assert averages.assertions == 1.0, "One or more eval cases failed — see the report above."
