"""Supervisor/worker multi-agent pattern.

Use this pattern when:
- A task can be broken into specialized subtasks
- Different agents have different tools, instructions, or output types
- You want a coordinator that *decides* which workers to call, and in what order

Architecture:
    supervisor_agent → decides which worker to call, and what to hand it
    analyst_agent    → researches a question and returns key findings
    writer_agent     → turns material into clear prose

The supervisor sees each worker as a tool. The model chooses whether to call the analyst, the
writer, both (and in which order), or neither — that choice is what separates this from
`pipeline` (fixed order, chosen by code) and `router` (one specialist, chosen by code).

To adapt it:
    1. Replace the workers with your own, each with its specialized tools and instructions
    2. Give the supervisor one delegation tool per worker
    3. Describe, in the supervisor's instructions, when each worker is the right call
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.runs import Flow, RunResult

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# Guardrail against runaway agentic loops. A run that exceeds any limit
# raises UsageLimitExceeded instead of silently burning tokens. Worker runs
# share the supervisor's budget (see the delegation tools), so this bounds
# the whole delegation tree, not just the supervisor's own requests. Set
# AGENT_COST_LIMIT (USD) to add a spend cap — optional, off by default, and only
# useful for models with known pricing (see Settings.cost_limit).
USAGE_LIMITS = UsageLimits(
    request_limit=12, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)


# --- Shared dependencies ---
@dataclass
class SharedDeps:
    """Dependencies shared across supervisor and worker agents."""

    pass


# --- Worker agents ---
# Each worker is a specialized agent with its own instructions and tools.


class Findings(BaseModel):
    points: list[str]


analyst_agent: Agent[SharedDeps, Findings] = Agent(
    settings.model,
    name=f"{LABEL}.analyst",  # helpers are labeled <agent>.<role>
    output_type=Findings,
    deps_type=SharedDeps,
    # Fail fast when the provider filters a response, instead of retrying a
    # refused request or returning partial text.
    capabilities=[RaiseContentFilterError()],
    instructions=(
        "You are an analyst. Given a question or topic, list its key findings as three to five "
        "short, factual points. Do not write prose; the points are handed to a writer."
    ),
)


class Draft(BaseModel):
    text: str


writer_agent: Agent[SharedDeps, Draft] = Agent(
    settings.model,
    name=f"{LABEL}.writer",
    output_type=Draft,
    deps_type=SharedDeps,
    capabilities=[RaiseContentFilterError()],
    instructions=(
        "You are a writer. Turn the material you are given into clear, concise prose that "
        "follows any instructions about length or audience. Use only the material provided."
    ),
)


# --- Supervisor agent ---
class SupervisorOutput(BaseModel):
    # `result` is the conventional output field in these examples; the generated
    # eval starter reads it when present (see evals/helpers.py).
    result: str
    steps_taken: list[str]


supervisor_agent: Agent[SharedDeps, SupervisorOutput] = Agent(
    settings.model,
    name=LABEL,
    output_type=SupervisorOutput,
    deps_type=SharedDeps,
    # Fail fast when the provider filters a response, instead of retrying a
    # refused request or returning partial text.
    capabilities=[RaiseContentFilterError()],
    instructions="""You coordinate two workers to answer the user's request.

    - delegate_to_analyst: researches a question and returns key findings.
    - delegate_to_writer: turns material into prose. It knows only what you pass it, so
      include the findings and any instructions about length or audience in `task`.

    For a request that needs research and a written answer, call the analyst first, then the
    writer with the analyst's findings. If one worker is enough, call only that one. Return
    the final text in `result`, and in `steps_taken` list each worker you called, in order.
    """,
)


# --- Supervisor tools that delegate to workers ---
@supervisor_agent.tool
async def delegate_to_analyst(ctx: RunContext[SharedDeps], task: str) -> str:
    """Ask the analyst to research a question or topic.

    Args:
        task: The question or topic to analyze.

    Returns:
        The analyst's key findings, one per line.
    """
    logger.info("Delegating to analyst", extra={"task": task})
    # usage=ctx.usage makes the worker's spend count against the supervisor
    # run's shared budget — the standard pydantic-ai delegation pattern.
    result = await analyst_agent.run(
        task, deps=ctx.deps, usage=ctx.usage, usage_limits=USAGE_LIMITS
    )
    return "\n".join(f"- {point}" for point in result.output.points)


@supervisor_agent.tool
async def delegate_to_writer(ctx: RunContext[SharedDeps], task: str) -> str:
    """Ask the writer to turn material into prose.

    Args:
        task: The material to write from, plus any instructions about length or audience.

    Returns:
        The written text.
    """
    logger.info("Delegating to writer", extra={"task": task})
    result = await writer_agent.run(task, deps=ctx.deps, usage=ctx.usage, usage_limits=USAGE_LIMITS)
    return result.output.text


async def run_supervisor(
    user_input: str, deps: SharedDeps | None = None
) -> RunResult[SupervisorOutput]:
    """Run the supervisor agent to coordinate workers on a task.

    Args:
        user_input: The user's message or task description.
        deps: Runtime dependencies. Created with defaults if not provided.

    Returns:
        A RunResult with one step, the supervisor's. The workers it delegated to ran inside
        that step (their calls are in `.all_messages()`), and `.usage` includes their spend.
    """
    if deps is None:
        deps = SharedDeps()
    logger.info("Running supervisor agent", extra={"user_input": user_input})
    flow = Flow(USAGE_LIMITS)
    result = await flow.run(supervisor_agent, user_input, deps=deps)
    return flow.finish(result.output)


if __name__ == "__main__":
    import asyncio

    configure_logging()
    result = asyncio.run(
        run_supervisor(
            "Research the pros and cons of remote work, then write two sentences about it for a manager."
        )
    )
    print(result.output)
