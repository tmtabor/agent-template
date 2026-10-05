"""Blank agent — an empty starting point with one agent, one output type, one prompt.

To use:
    1. Define your output type (or use str for unstructured output)
    2. Set your instructions in agent/prompts/blank.txt
    3. Add tools if needed
    4. Call run_blank_agent()
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import (  # noqa: F401 — RunContext used in commented tool example below
    Agent,
    RunContext,
)
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import configure_logging, get_logger
from agent.prompts.templates import load_prompt

logger = get_logger(__name__)

# Guardrail against runaway agentic loops. A run that exceeds any limit
# raises UsageLimitExceeded instead of silently burning tokens. Tune per task:
# request_limit caps model round-trips (each tool-call iteration is one
# request), total_tokens_limit caps overall tokens. Set AGENT_COST_LIMIT (USD) to
# add a spend cap — optional, off by default, and only useful for models with
# known pricing (see Settings.cost_limit).
USAGE_LIMITS = UsageLimits(
    request_limit=10, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)


# --- Output type ---
# Replace with your actual output schema, or use str for unstructured output.
class BlankOutput(BaseModel):
    """Replace with your actual output schema."""

    result: str


# --- Dependencies ---
# Use a dataclass to inject runtime dependencies (DB connections, API clients, etc.)
# Remove if this agent needs no external dependencies.
@dataclass
class BlankDeps:
    """Runtime dependencies injected into the blank agent."""

    # example_client: SomeAPIClient  # Add your dependencies here
    pass


# --- Agent definition ---
blank_agent: Agent[BlankDeps, BlankOutput] = Agent(
    settings.model,
    name="blank",  # labels this agent's run span in Logfire traces
    output_type=BlankOutput,
    deps_type=BlankDeps,
    # Fail fast when the provider filters a response, instead of retrying a
    # refused request or returning partial text.
    capabilities=[RaiseContentFilterError()],
    instructions=load_prompt("blank"),  # loads agent/prompts/blank.txt
)


# --- Tools ---
# Add tools here. See agent/tools/example.py for the full pattern.
# @blank_agent.tool
# async def my_tool(ctx: RunContext[BlankDeps], query: str) -> str:
#     """Tool description — this docstring is sent to the LLM."""
#     return "result"


# --- Dynamic instructions (optional) ---
# Use @blank_agent.instructions for instructions that depend on runtime state.
# @blank_agent.instructions
# async def dynamic_instructions(ctx: RunContext[BlankDeps]) -> str:
#     return f"Today is {date.today()}."


async def run_blank_agent(user_input: str, deps: BlankDeps | None = None) -> BlankOutput:
    """Run the blank agent with the given user input.

    Args:
        user_input: The user's message or task description.
        deps: Runtime dependencies. Created with defaults if not provided.

    Returns:
        Validated BlankOutput instance.
    """
    if deps is None:
        deps = BlankDeps()

    logger.info("Running blank agent", extra={"user_input": user_input})

    result = await blank_agent.run(user_input, deps=deps, usage_limits=USAGE_LIMITS)

    logger.info("Blank agent run complete", extra={"output": result.output})
    return result.output


if __name__ == "__main__":
    import asyncio

    configure_logging()
    output = asyncio.run(run_blank_agent("Hello, what can you do?"))
    print(output)
