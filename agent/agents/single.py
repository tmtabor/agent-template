"""Single-agent pattern: one agent handles the entire task.

This is the simplest pattern — use it when:
- One agent can handle the full task
- No specialization or delegation is needed
- You want the lowest complexity

To use:
    1. Define your output type (or use str for unstructured output)
    2. Set your instructions
    3. Add tools if needed
    4. Call run_agent()
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import (  # noqa: F401 — RunContext used in commented tool example below
    Agent,
    RunContext,
)
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import configure_logging, get_logger
from agent.prompts.templates import load_prompt

logger = get_logger(__name__)

# Guardrail against runaway agentic loops. A run that exceeds either limit
# raises UsageLimitExceeded instead of silently burning tokens. Tune per task:
# request_limit caps model round-trips (each tool-call iteration is one
# request), total_tokens_limit caps overall spend for the run.
USAGE_LIMITS = UsageLimits(request_limit=10, total_tokens_limit=100_000)


# --- Output type ---
# Replace with your actual output schema, or use str for unstructured output.
class AgentOutput(BaseModel):
    """Replace with your actual output schema."""

    result: str
    confidence: float


# --- Dependencies ---
# Use a dataclass to inject runtime dependencies (DB connections, API clients, etc.)
# Remove if your agent needs no external dependencies.
@dataclass
class AgentDeps:
    """Runtime dependencies injected into the agent."""

    # example_client: SomeAPIClient  # Add your dependencies here
    pass


# --- Agent definition ---
agent: Agent[AgentDeps, AgentOutput] = Agent(
    settings.model,
    name="agent",  # labels this agent's run span in Logfire traces
    output_type=AgentOutput,
    deps_type=AgentDeps,
    instructions=load_prompt("system"),  # loads agent/prompts/system.txt
    # Or inline: instructions="You are a helpful assistant."
)


# --- Tools ---
# Add tools here. See agent/tools/example.py for the full pattern.
# @agent.tool
# async def my_tool(ctx: RunContext[AgentDeps], query: str) -> str:
#     """Tool description — this docstring is sent to the LLM."""
#     return "result"


# --- Dynamic instructions (optional) ---
# Use @agent.instructions for instructions that depend on runtime state.
# @agent.instructions
# async def dynamic_instructions(ctx: RunContext[AgentDeps]) -> str:
#     return f"Today is {date.today()}."


async def run_agent(user_input: str, deps: AgentDeps | None = None) -> AgentOutput:
    """Run the agent with the given user input.

    Args:
        user_input: The user's message or task description.
        deps: Runtime dependencies. Created with defaults if not provided.

    Returns:
        Validated AgentOutput instance.
    """
    if deps is None:
        deps = AgentDeps()

    logger.info("Running single agent", extra={"user_input": user_input})

    result = await agent.run(user_input, deps=deps, usage_limits=USAGE_LIMITS)

    logger.info("Agent run complete", extra={"output": result.output})
    return result.output


# --- Multi-turn conversation example ---
# To maintain conversation history across multiple calls:
#
# history = []
# result1 = await agent.run("First message", deps=deps)
# history = result1.all_messages()
#
# result2 = await agent.run("Follow-up", deps=deps, message_history=history)
# history = result2.all_messages()
#
# Use all_messages(), not new_messages(), when carrying history forward —
# new_messages() returns only the messages from that single run, so assigning
# it to history would silently drop all earlier turns.


if __name__ == "__main__":
    import asyncio

    configure_logging()
    output = asyncio.run(run_agent("Hello, what can you do?"))
    print(output)
