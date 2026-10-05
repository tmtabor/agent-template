"""Evaluator–optimizer: a generator drafts, a critic reviews, and they loop until it passes.

Use this pattern when:
- You can state what "good" looks like as criteria a second model can check
- A first attempt is usually close but benefits from targeted revision
- The cost of a few extra model calls is worth a better final answer

    generator → draft → critic ─ accepted ─→ done
         ▲                │
         └── feedback ────┘   (at most MAX_ITERATIONS rounds)

The loop is bounded twice: by an explicit round cap, and by `USAGE_LIMITS`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.usage import RunUsage, UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.prompts.templates import load_prompt

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# Each round costs two requests (generate + critique). Size request_limit for the cap below.
USAGE_LIMITS = UsageLimits(
    request_limit=12, total_tokens_limit=150_000, cost_limit=settings.cost_limit
)

# Hard cap on revise rounds. Without one, a critic that is never satisfied loops until
# USAGE_LIMITS trips; with one, you decide what "good enough" means.
MAX_ITERATIONS = 3


@dataclass
class EvaluatorOptimizerDeps:
    """Runtime dependencies shared by the generator and the critic."""

    pass


class Draft(BaseModel):
    result: str


generator_agent: Agent[EvaluatorOptimizerDeps, Draft] = Agent(
    settings.model,
    name=f"{LABEL}.generator",
    output_type=Draft,
    deps_type=EvaluatorOptimizerDeps,
    capabilities=[RaiseContentFilterError()],
    instructions=load_prompt("evaluator_optimizer_generator"),
)


class Critique(BaseModel):
    accepted: bool
    feedback: str


critic_agent: Agent[EvaluatorOptimizerDeps, Critique] = Agent(
    settings.model,
    name=f"{LABEL}.critic",
    output_type=Critique,
    deps_type=EvaluatorOptimizerDeps,
    capabilities=[RaiseContentFilterError()],
    instructions=load_prompt("evaluator_optimizer_critic"),
)


class EvaluatorOptimizerOutput(BaseModel):
    result: str
    # False means the round cap was hit: `result` is the best draft so far, not a passing one.
    accepted: bool
    iterations: int


async def run_evaluator_optimizer(
    user_input: str, deps: EvaluatorOptimizerDeps | None = None
) -> EvaluatorOptimizerOutput:
    """Draft a description of `user_input`, revising until the critic accepts or the cap is hit.

    Hitting the cap returns the last draft with `accepted=False` rather than raising; the
    caller decides whether that is good enough.
    """
    if deps is None:
        deps = EvaluatorOptimizerDeps()
    usage = RunUsage()  # shared, so USAGE_LIMITS bounds every round
    run_args = {"deps": deps, "usage": usage, "usage_limits": USAGE_LIMITS}

    prompt = f"Item: {user_input}"
    draft = ""
    for iteration in range(1, MAX_ITERATIONS + 1):
        draft = (await generator_agent.run(prompt, **run_args)).output.result
        critique = (
            await critic_agent.run(f"Item: {user_input}\n\nDescription:\n{draft}", **run_args)
        ).output
        logger.info("Reviewed", extra={"iteration": iteration, "accepted": critique.accepted})
        if critique.accepted:
            return EvaluatorOptimizerOutput(result=draft, accepted=True, iterations=iteration)
        # Feed the critic's feedback back in, along with the draft it was about.
        prompt = (
            f"Item: {user_input}\n\nPrevious attempt:\n{draft}\n\nFeedback to address:\n"
            f"{critique.feedback}"
        )

    return EvaluatorOptimizerOutput(result=draft, accepted=False, iterations=MAX_ITERATIONS)


if __name__ == "__main__":
    import asyncio

    configure_logging()
    print(asyncio.run(run_evaluator_optimizer("A stainless steel water bottle")))
