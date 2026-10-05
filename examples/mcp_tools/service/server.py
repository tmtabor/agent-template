"""The calendar MCP server: a standalone service that an agent connects to over HTTP.

This is the *other half* of the `mcp_tools` example. It knows nothing about agents or models: it
exposes three date tools over the Model Context Protocol, and any MCP client (the agent in
../agent.py, an IDE, another application) can call them. It runs as its own process, started by
Docker Compose (see docker-compose.yml) or directly:

    uv run --with "fastmcp-slim[server]>=4.0,<5" python server.py     # http://127.0.0.1:8000/mcp

Dates are a good fit for a tool: models are unreliable at calendar arithmetic, and a tool makes it
exact. Replace these tools with your own; the agent discovers whatever the server offers.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from fastmcp import FastMCP

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


def main() -> None:
    """Serve over streamable HTTP. Inside a container MCP_HOST is 0.0.0.0 so the port can be published."""
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8000"))
    server.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
