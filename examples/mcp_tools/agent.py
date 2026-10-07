"""MCP tools: give an agent the tools of a Model Context Protocol server running as a service.

Use this pattern when:
- The tools already exist as an MCP server (yours, or someone else's) and the agent should use them
- One tool implementation should serve several clients (this agent, an IDE, another application)
- Tools should be discovered at run time rather than hard-coded into the agent

How it works: the server is its own process (`service/server.py`, started by Docker Compose). The
agent connects to it by URL, lists its tools, and exposes them to the model like any other. When the
model calls one, the call goes over the network to the server and the result comes back. A tool that
raises becomes an error the model sees and can correct (here, a malformed date).

The server's address is a dependency (`McpDeps.server_url`, read from MCP_SERVER_URL), so the same agent
can talk to the local service, a staging server or a test double. The toolset is built per run from it.
Pointing at a different MCP server changes nothing else: its tools are discovered, not coded.

If the server isn't running, `run_mcp` raises `McpServerUnavailable` saying where it looked.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.mcp import MCPToolset
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

# The server's own port, for a server you start yourself on it. The Docker service publishes on a random
# free host port instead, so set MCP_SERVER_URL to the address `docker compose port` shows (see service/).
DEFAULT_SERVER_URL = "http://127.0.0.1:8000/mcp"


def server_url_from_env() -> str:
    return os.environ.get("MCP_SERVER_URL", DEFAULT_SERVER_URL)


# --- Dependencies ---
@dataclass
class McpDeps:
    """Runtime dependencies for the MCP agent."""

    server_url: str = field(default_factory=server_url_from_env)


class McpServerUnavailable(Exception):
    """The MCP server could not be reached."""


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
    capabilities=[RaiseContentFilterError()],
    instructions=(
        "You answer questions about dates and the calendar. Use the tools for every calculation "
        "and never work out dates yourself. Dates are written YYYY-MM-DD."
    ),
)


@mcp_agent.toolset(per_run_step=False)
def calendar_tools(ctx: RunContext[McpDeps]) -> MCPToolset:
    """The MCP server's tools, connected to the address in deps. Built once per run."""
    return MCPToolset(ctx.deps.server_url)


async def run_mcp(user_input: str, deps: McpDeps | None = None) -> RunResult[Answer]:
    """Answer a calendar question using the MCP server's tools.

    Returns:
        A RunResult: `.output` is the `Answer`; the MCP tool calls and results are in
        `.all_messages()`.

    Raises:
        McpServerUnavailable: When the server can't be reached.
    """
    if deps is None:
        deps = McpDeps()
    logger.info("Running MCP agent", extra={"user_input": user_input, "server": deps.server_url})
    flow = Flow(USAGE_LIMITS)
    try:
        result = await flow.run(mcp_agent, user_input, deps=deps)
    except RuntimeError as exc:
        # fastmcp reports a refused or unreachable connection as a RuntimeError; anything else is a bug.
        if "failed to connect" not in str(exc):
            raise
        raise McpServerUnavailable(
            f"No MCP server at {deps.server_url}. Start it with "
            "`docker compose -f examples/mcp_tools/service/docker-compose.yml up -d --wait`, "
            "or set MCP_SERVER_URL."
        ) from exc
    return flow.finish(result.output)


if __name__ == "__main__":
    import asyncio

    configure_logging()
    question = (
        "How many days are there from 2024-02-10 to 2024-03-01, and what weekday is 2024-12-25?"
    )
    print(asyncio.run(run_mcp(question)).output)
