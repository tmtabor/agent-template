"""Pipeline (prompt chain): fixed sequential steps, each one's output feeding the next.

Use this pattern when:
- The task decomposes into stages that always run in the same order
- Each stage is easier and more reliable as its own focused prompt
- You want to check intermediate results and stop early, rather than trust one long prompt

    outline → draft → polish          (code decides the order; the model never does)

Unlike `supervisor`, nothing here is chosen by the LLM: the control flow is ordinary Python,
so it is cheap to reason about, test and bound.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.runs import Flow, RunResult

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# One budget for the whole chain: every step runs in one Flow (see run_pipeline).
USAGE_LIMITS = UsageLimits(
    request_limit=15, total_tokens_limit=150_000, cost_limit=settings.cost_limit
)


@dataclass
class PipelineDeps:
    """Runtime dependencies shared by every step."""

    pass


def _step(role: str, output_type: type[BaseModel], instructions: str) -> Agent:
    return Agent(
        settings.model,
        name=f"{LABEL}.{role}",
        output_type=output_type,
        deps_type=PipelineDeps,
        capabilities=[RaiseContentFilterError()],
        instructions=instructions,
    )


# --- Step 1: outline ---
class Outline(BaseModel):
    points: list[str]


outline_agent: Agent[PipelineDeps, Outline] = _step(
    "outline",
    Outline,
    "Write a short outline for a piece on the given topic: three to five key points, each a "
    "single sentence.",
)


# --- Step 2: draft ---
class Draft(BaseModel):
    text: str


draft_agent: Agent[PipelineDeps, Draft] = _step(
    "draft",
    Draft,
    "Write a first draft from the outline you are given. Cover every point, in order.",
)


# --- Step 3: polish ---
class PipelineOutput(BaseModel):
    result: str
    outline: list[str]


class Polished(BaseModel):
    result: str


polish_agent: Agent[PipelineDeps, Polished] = _step(
    "polish",
    Polished,
    "Edit the draft for clarity and concision. Keep its meaning and structure.",
)


class EmptyOutlineError(Exception):
    """The outline step produced nothing to draft from."""


async def run_pipeline(
    user_input: str, deps: PipelineDeps | None = None
) -> RunResult[PipelineOutput]:
    """Write a short piece on `user_input` in three chained steps.

    Returns:
        A RunResult: `.output` is the PipelineOutput; `.steps` holds the outline, draft and
        polish steps in order.

    Raises:
        EmptyOutlineError: When step 1 returns no points. Failing here is the payoff of a
            chain: the later steps never spend tokens on nothing.
    """
    if deps is None:
        deps = PipelineDeps()
    flow = Flow(USAGE_LIMITS)  # one shared budget, so USAGE_LIMITS bounds the whole chain

    outline = (await flow.run(outline_agent, f"Topic: {user_input}", deps=deps)).output
    # A gate between steps: plain code checking the previous step's typed output.
    if not outline.points:
        raise EmptyOutlineError(f"No outline was produced for: {user_input!r}")
    logger.info("Outline ready", extra={"points": len(outline.points)})

    numbered = "\n".join(f"{i}. {point}" for i, point in enumerate(outline.points, 1))
    draft = (await flow.run(draft_agent, f"Outline:\n{numbered}", deps=deps)).output
    polished = (await flow.run(polish_agent, f"Draft:\n{draft.text}", deps=deps)).output

    return flow.finish(PipelineOutput(result=polished.result, outline=outline.points))


if __name__ == "__main__":
    import asyncio

    configure_logging()
    print(asyncio.run(run_pipeline("Why unit tests are worth writing")).output)
