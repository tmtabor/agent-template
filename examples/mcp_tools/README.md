# MCP tools

Give an agent the tools of a Model Context Protocol (MCP) server.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

**Use it when** the tools already exist as an MCP server (yours, or someone else's), one tool
implementation should serve several clients, or tools should be discovered at run time instead of
hard-coded into the agent.

```
agent ──MCP(local=server)──▶ server: days_between · add_days · weekday
  ▲                                │
  └────────── tool result ◀────────┘
```

**What it shows**

- **The `MCP` capability:** the agent connects to a server, lists its tools and exposes them to the
  model like any other. Calls go over real MCP and results come back
- **An in-process server** (`FastMCP`), so the whole example is one file with no subprocess or
  network. The tools are plain functions, so they are tested directly
- **Swapping the server is one argument.** Replace `MCP(local=server)` with a URL
  (`MCP("https://example.com/mcp")`) or a command
  (`MCP(local=StdioTransport(command="uvx", args=["some-mcp-server"]))`) and nothing else changes
- **Server errors the model can fix:** a malformed date raises in the tool, and the model sees
  `Error calling tool 'days_between': 'next tuesday' is not a date. Use the form YYYY-MM-DD` and
  retries with a correct one
- **A real dependency:** this is the first example that needs a package the template doesn't
  (`fastmcp-slim[server]`). `add_agent.py` installs it with `uv add`, and the release check runs
  the example in its own environment

```bash
uv run python scripts/add_agent.py mcp_tools --name calendar
```

Dates are a good fit for a tool: models are unreliable at calendar arithmetic, and a tool makes it
exact. To expose these tools to other MCP clients, run the server on its own with `server.run()`.
