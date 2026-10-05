"""MCP tools: give an agent the tools of a Model Context Protocol server.

Use this pattern when:
- The tools already exist as an MCP server (yours, or someone else's) and you want the agent to use them
- You want one tool implementation to serve several clients (this agent, an IDE, another app)
- Tools should be discovered at run time rather than hard-coded into the agent

How it works: the agent gets an `MCP(...)` capability, which connects to a server, lists its tools,
and exposes them to the model like any other tool. When the model calls one, the call goes over MCP to
the server and the result comes back. A tool that raises becomes an error the model sees and can
correct (here, a malformed date).

This example runs a small calendar server **in process** (`MCP(local=server)`), so the whole example
is one file and needs no subprocess or network. The model still talks to it over real MCP. To use a
different server, change that one argument: a URL (`MCP("https://…/mcp")`) or a command
(`MCP(local=StdioTransport(command="uvx", args=["some-mcp-server"]))`). Everything else stays.

Dates are a good fit: models are unreliable at calendar arithmetic, and a tool makes it exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from fastmcp import FastMCP
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.capabilities import MCP, RaiseContentFilterError
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.runs import Flow, RunResult

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# Each tool call is a model round trip, so a few questions in one need headroom.
USAGE_LIMITS = UsageLimits(
    request_limit=12, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)


# --- The MCP server ---
# In a real system this lives elsewhere (its own process, or a service you don't own). It is
# defined here so the example is self-contained and its tools can be tested directly.
server = FastMCP("calendar-tools")


def parse_date(text: str) -> date:
    """A date from `YYYY-MM-DD`, or a ValueError the model can read and fix."""
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        raise ValueError(
            f"{text!r} is not a date. Use the form YYYY-MM-DD, e.g. 2025-03-01."
        ) from None


@server.tool
def days_between(start: str, end: str) -> int:
    """The number of days from `start` to `end`: negative if `end` is earlier. Dates are YYYY-MM-DD."""
    return (parse_date(end) - parse_date(start)).days


@server.tool
def add_days(start: str, days: int) -> str:
    """The date `days` days after `start` (before it, if negative), as YYYY-MM-DD."""
    return (parse_date(start) + timedelta(days=days)).isoformat()


@server.tool
def weekday(day: str) -> str:
    """The day of the week a date falls on, e.g. "Wednesday". The date is YYYY-MM-DD."""
    return parse_date(day).strftime("%A")


# --- Dependencies ---
@dataclass
class McpDeps:
    """Runtime dependencies for the MCP agent."""

    pass


# --- Output type ---
class Answer(BaseModel):
    # `result` is the conventional output field in these examples; the generated
    # eval starter reads it when present (see evals/helpers.py).
    result: str


# --- Agent ---
mcp_agent: Agent[McpDeps, Answer] = Agent(
    settings.model,
    name=LABEL,
    output_type=Answer,
    deps_type=McpDeps,
    capabilities=[
        RaiseContentFilterError(),
        MCP(
            local=server
        ),  # connect to the server and expose its tools; swap this for a URL or stdio
    ],
    instructions=(
        "You answer questions about dates and the calendar. Use the tools for every calculation "
        "and never work out dates yourself. Dates are written YYYY-MM-DD."
    ),
)


async def run_mcp(user_input: str, deps: McpDeps | None = None) -> RunResult[Answer]:
    """Answer a calendar question using the MCP server's tools.

    Returns:
        A RunResult: `.output` is the `Answer`; the MCP tool calls and results are in
        `.all_messages()`.
    """
    if deps is None:
        deps = McpDeps()
    logger.info("Running MCP agent", extra={"user_input": user_input})
    flow = Flow(USAGE_LIMITS)
    result = await flow.run(mcp_agent, user_input, deps=deps)
    return flow.finish(result.output)


if __name__ == "__main__":
    import asyncio

    configure_logging()
    question = (
        "How many days are there from 2024-02-10 to 2024-03-01, and what weekday is 2024-12-25?"
    )
    print(asyncio.run(run_mcp(question)).output)
