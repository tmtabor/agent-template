"""Shared helpers for the eval starters that `scripts/add_agent.py` generates.

Each agent's evals/test_<name>.py is a thin file over these, so the evaluators and
budgets live in one place. Run evals with: uv run pytest -m eval
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

from agent.runs import RunResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Behavioral budgets, applied to every case. These are span-based evaluators:
# they grade how the agent got to its answer, not just the answer, and need
# the Logfire/OpenTelemetry setup in evals/conftest.py to capture spans (without
# spans they fail with a "no span tree" reason). Keep them comfortably below the
# agent's USAGE_LIMITS.request_limit — a run that merely scrapes under the hard
# limit is still a looping run.
MAX_MODEL_REQUESTS = 5
MAX_TOOL_CALLS = 4


def output_text(output: Any) -> str:
    """The agent's answer as text: its `result` field if it has one, else str(output)."""
    return str(output.result) if hasattr(output, "result") else str(output)


def load_fixtures(name: str) -> list[dict]:
    """Load evals/fixtures/<name>.json."""
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


@dataclass
class ContainsExpected(Evaluator[str, str]):
    """Pass if the expected output appears in the answer (case-insensitive).

    Cases without an expected_output just need a non-empty answer.
    """

    def evaluate(self, ctx: EvaluatorContext[str, str]) -> bool:
        if ctx.expected_output is None:
            return bool(ctx.output and ctx.output.strip())
        return ctx.expected_output.lower() in ctx.output.lower()


def case_evaluators(fixture: dict) -> list[Evaluator]:
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


async def run_fixture_dataset(
    name: str, fixtures: list[dict], run: Callable[[str], Awaitable[RunResult]]
) -> None:
    """Run every fixture case through `run` (a run helper) and assert they all pass.

    Add cases to the JSON file to grow the eval — no code changes needed unless a case
    requires a new kind of check, in which case add an Evaluator like ContainsExpected.
    """
    dataset = Dataset(
        name=name,
        cases=[
            Case(
                name=fixture["name"],
                inputs=fixture["inputs"]["user_input"],
                expected_output=fixture.get("expected_output"),
                metadata=fixture.get("metadata"),
                evaluators=case_evaluators(fixture),
            )
            for fixture in fixtures
        ],
        evaluators=[
            ContainsExpected(),
            MaxModelRequests(max_requests=MAX_MODEL_REQUESTS),
            MaxToolCalls(max_calls=MAX_TOOL_CALLS),
        ],
    )

    async def task(user_input: str) -> str:
        return output_text((await run(user_input)).output)

    report = await dataset.evaluate(task)
    report.print(include_input=True, include_output=True)

    averages = report.averages()
    assert averages is not None
    assert averages.assertions == 1.0, "One or more eval cases failed — see the report above."
