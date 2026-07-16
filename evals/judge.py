"""LLM-as-judge evaluator for semantic quality scoring.

Uses a separate judge model (settings.judge_model) to evaluate agent outputs.
The judge should be a *different* model from the agent under test to avoid
self-assessment bias, but at least as capable — a weak judge grading a strong
agent introduces its own bias.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from agent.config import settings


class JudgeScore(BaseModel):
    """Structured output produced by the judge model."""

    score: float = Field(ge=0.0, le=1.0)
    reasoning: str


@dataclass
class JudgeVerdict:
    """Judge score plus the threshold decision.

    `passed` is computed from the threshold, never LLM-generated — don't ask
    the model to produce a value the code immediately overwrites.
    """

    score: float
    reasoning: str
    passed: bool


judge_agent: Agent[None, JudgeScore] = Agent(
    settings.judge_model,
    name="judge",  # labels this agent's run span in Logfire traces
    output_type=JudgeScore,
    instructions="""You are an impartial evaluator assessing AI agent outputs.

    Score the response on a scale of 0.0 to 1.0:
    - 1.0: Perfect response, fully addresses the task
    - 0.7-0.9: Good response with minor issues
    - 0.4-0.6: Partial response, addresses some but not all requirements
    - 0.0-0.3: Poor response, fails to address the task

    Be objective and focus on whether the response fulfills the stated requirements.
    """,
)


async def judge_response(
    task: str,
    response: str,
    criteria: str,
    threshold: float = 0.7,
) -> JudgeVerdict:
    """Evaluate a response using an LLM judge.

    Args:
        task: The original task or question given to the agent.
        response: The agent's response to evaluate.
        criteria: Specific criteria the response should meet.
        threshold: Minimum score to pass (default 0.7).

    Returns:
        JudgeVerdict with score, reasoning, and pass/fail.
    """
    prompt = f"""Task: {task}

Response to evaluate:
{response}

Evaluation criteria:
{criteria}

Score this response and explain your reasoning."""

    result = await judge_agent.run(prompt)
    score = result.output
    return JudgeVerdict(
        score=score.score,
        reasoning=score.reasoning,
        passed=score.score >= threshold,
    )
