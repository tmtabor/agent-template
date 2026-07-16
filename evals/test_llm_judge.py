"""LLM-as-judge eval examples.

These evals use a separate LLM (settings.judge_model) to evaluate output
quality. They require an API key and cost money to run.
Run with: uv run pytest -m eval  (runs alongside the pass/fail evals)
"""

import pytest

from agent.agents import run_agent
from evals.judge import judge_response


@pytest.mark.eval
async def test_agent_quality_judge():
    """LLM judge evaluates response quality."""
    task = "Explain what an AI agent is in one sentence."
    output = await run_agent(task)

    verdict = await judge_response(
        task=task,
        response=output.result,
        criteria="The response should be a single sentence that accurately "
        "describes what an AI agent is. It should be clear and concise.",
        threshold=0.7,
    )

    assert verdict.passed, (
        f"Judge score {verdict.score:.2f} below threshold. Reasoning: {verdict.reasoning}"
    )


@pytest.mark.eval
async def test_agent_relevance_judge():
    """LLM judge evaluates whether response is relevant to the task."""
    task = "List three benefits of Python for data science."
    output = await run_agent(task)

    verdict = await judge_response(
        task=task,
        response=output.result,
        criteria="The response should list exactly three distinct benefits of Python "
        "specifically for data science use cases.",
        threshold=0.6,
    )

    assert verdict.passed, (
        f"Relevance score {verdict.score:.2f} below threshold. Reasoning: {verdict.reasoning}"
    )
