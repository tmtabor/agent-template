"""Tool-calling agent pattern.

Use this pattern when:
- The agent needs to interact with external systems (APIs, databases, files)
- You want the LLM to decide which tools to call and when
- Tool results inform subsequent decisions (agentic loop)

Key design principles (from production experience):
- Keep tool interfaces simple: fewer optional params = more reliable tool selection
- Translate errors into English: give the LLM enough context to self-correct
- Hold large payloads at the tool layer: don't dump raw API responses into context

See agent/tools/example.py for the full tool implementation pattern.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import configure_logging, get_logger

logger = get_logger(__name__)

# Guardrail against runaway agentic loops. A run that exceeds either limit
# raises UsageLimitExceeded instead of silently burning tokens. Tune per task:
# request_limit caps model round-trips (each tool-call iteration is one
# request), total_tokens_limit caps overall spend for the run.
USAGE_LIMITS = UsageLimits(request_limit=10, total_tokens_limit=100_000)


# --- Dependencies ---
@dataclass
class ToolAgentDeps:
    """Runtime dependencies for the tool-calling agent."""

    # Add API clients, DB connections, etc.
    # example (requires `from dataclasses import field`):
    # api_client: MyAPIClient = field(default_factory=MyAPIClient)
    pass


# --- Output type ---
class ToolAgentOutput(BaseModel):
    # `result` is the canonical output field shared by all three stubs —
    # keep it (or rename it consistently) so evals/ stays pattern-agnostic.
    result: str
    # Pydantic deep-copies mutable defaults, so a plain [] is safe here.
    # Do NOT use dataclasses.field() inside a BaseModel — it is not a
    # Pydantic construct (use pydantic.Field(default_factory=...) if needed).
    tools_used: list[str] = []


# --- Agent ---
tool_agent: Agent[ToolAgentDeps, ToolAgentOutput] = Agent(
    settings.model,
    name="tool_agent",  # labels this agent's run span in Logfire traces
    output_type=ToolAgentOutput,
    deps_type=ToolAgentDeps,
    instructions="""You are an agent with access to tools.

    Use tools when you need external information or to take actions.
    If a tool fails, read the error message carefully — it will tell you how to recover.
    """,
)


# --- Tools ---
# See agent/tools/example.py for the full pattern with proper error handling.


@tool_agent.tool
async def example_tool(ctx: RunContext[ToolAgentDeps], query: str) -> str:
    """Search for information about the given query.

    Args:
        query: What to search for. Be specific.

    Returns:
        Relevant information as a string.

    Raises:
        ModelRetry: When the tool fails in a way the LLM can correct.
    """
    try:
        # Replace with real implementation
        logger.info("Tool called", extra={"tool": "example_tool", "query": query})
        return f"Result for: {query}"
    except ValueError as e:
        # Translate errors into English so the LLM can self-correct
        raise ModelRetry(
            f"Invalid query format: {e}. Please provide a query as a plain text string."
        ) from e
    except Exception as e:
        # Unrecoverable: log and re-raise. ModelRetry is only for errors the
        # LLM can correct by changing its input (see agent/tools/example.py).
        logger.error("Tool failed", extra={"tool": "example_tool", "error": str(e)})
        raise


async def run_tool_agent(user_input: str, deps: ToolAgentDeps | None = None) -> ToolAgentOutput:
    """Run the tool-calling agent.

    Args:
        user_input: The user's message or task description.
        deps: Runtime dependencies. Created with defaults if not provided.
    """
    if deps is None:
        deps = ToolAgentDeps()
    logger.info("Running tool-calling agent", extra={"user_input": user_input})
    result = await tool_agent.run(user_input, deps=deps, usage_limits=USAGE_LIMITS)
    return result.output


if __name__ == "__main__":
    import asyncio

    configure_logging()
    output = asyncio.run(run_tool_agent("What can you find out about Python 3.13?"))
    print(output)
