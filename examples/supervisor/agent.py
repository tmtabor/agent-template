"""Supervisor/worker multi-agent pattern.

Use this pattern when:
- A task can be broken into specialized subtasks
- Different agents have different tools, instructions, or output types
- You want a coordinator to manage escalation and routing

Architecture:
    supervisor_agent → decides which worker to call
    worker_agent_a   → handles task type A
    worker_agent_b   → handles task type B

To use:
    1. Define worker agents with their specialized tools and instructions
    2. Give the supervisor tools that delegate to workers
    3. The supervisor orchestrates; workers execute
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
# share the supervisor's budget (see delegate_to_worker_a), so this bounds
# the whole delegation tree, not just the supervisor's own requests. Set
# AGENT_COST_LIMIT (USD) to add a spend cap — optional, off by default, and only
# useful for models with known pricing (see Settings.cost_limit).
USAGE_LIMITS = UsageLimits(
    request_limit=10, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)


# --- Shared dependencies ---
@dataclass
class SharedDeps:
    """Dependencies shared across supervisor and worker agents."""

    pass


# --- Worker agents ---
# Each worker is a specialized agent with its own instructions and tools.


class WorkerAOutput(BaseModel):
    result: str


worker_agent_a: Agent[SharedDeps, WorkerAOutput] = Agent(
    settings.model,
    name=f"{LABEL}.worker_a",  # helpers are labeled <agent>.<role>
    output_type=WorkerAOutput,
    deps_type=SharedDeps,
    # Fail fast when the provider filters a response, instead of retrying a
    # refused request or returning partial text.
    capabilities=[RaiseContentFilterError()],
    instructions="You are a specialist in [TASK TYPE A]. [Add specific instructions.]",
)

# Add worker_agent_b, worker_agent_c etc. as needed


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
    instructions="""You are a supervisor coordinating specialized workers.

    Analyze the task, delegate to the appropriate worker, and synthesize results.
    Use the available delegation tools to call workers.
    """,
)


# --- Supervisor tools that delegate to workers ---
@supervisor_agent.tool
async def delegate_to_worker_a(ctx: RunContext[SharedDeps], task: str) -> str:
    """Delegate a [TASK TYPE A] task to the specialized worker.

    Args:
        task: The specific task for the worker to complete.

    Returns:
        The worker's result as a string.
    """
    logger.info("Delegating to worker A", extra={"task": task})
    # usage=ctx.usage makes the worker's spend count against the supervisor
    # run's shared budget — the standard pydantic-ai delegation pattern.
    result = await worker_agent_a.run(
        task, deps=ctx.deps, usage=ctx.usage, usage_limits=USAGE_LIMITS
    )
    return result.output.result


# Add more delegation tools for other workers


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
    result = asyncio.run(run_supervisor("Complete this complex task..."))
    print(result.output)
