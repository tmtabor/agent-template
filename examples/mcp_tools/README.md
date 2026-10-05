# MCP tools

Give an agent the tools of a Model Context Protocol (MCP) server that runs as its own service.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

**Use it when** the tools already exist as an MCP server (yours, or someone else's), one tool
implementation should serve several clients (this agent, an IDE, another application), or tools
should be discovered at run time instead of hard-coded into the agent.

```
agent  ──── HTTP / MCP ────▶  service: days_between · add_days · weekday
(this process)                (its own container, started by Docker Compose)
   ▲                                   │
   └──────────── tool result ◀─────────┘
```

**What it shows**

- **A real service boundary.** The server (`service/server.py`) is a separate process with its own
  `Dockerfile` and `docker-compose.yml`. The agent reaches it over the network, so the tools are
  discovered across a wire, and the server can be written in anything, run anywhere, and shared
- **The address is a dependency.** `McpDeps.server_url` (read from `MCP_SERVER_URL`, defaulting to
  the local service) feeds a toolset the agent builds per run (`@agent.toolset`), so the same agent
  can use a staging server or a test double. Pointing it at a different MCP server changes nothing
  else: the tools are discovered, not coded
- **Server errors the model can fix:** a malformed date raises in the tool, and the model sees
  `Error calling tool 'days_between': 'next tuesday' is not a date. Use the form YYYY-MM-DD` and
  retries with a correct one
- **A server that isn't there:** `run_mcp` raises `McpServerUnavailable` saying where it looked and
  how to start it, instead of a bare connection error
- **Tested for real.** The offline tests run the same server as a local subprocess and talk to it
  over HTTP; the release check builds the Docker image, waits for its healthcheck, finds the port
  Docker chose, and runs the live tests and a recorded run against the container

## Running it

```bash
docker compose -f examples/mcp_tools/service/docker-compose.yml up -d --wait
PORT=$(docker compose -f examples/mcp_tools/service/docker-compose.yml port mcp-server 8000 | cut -d: -f2)
MCP_SERVER_URL=http://127.0.0.1:$PORT/mcp uv run python -m examples.mcp_tools.agent
docker compose -f examples/mcp_tools/service/docker-compose.yml down
```

To use it in your project, `add_agent.py` copies the agent into `agent/agents/` and the service into
`services/<name>/`, and tells you how to start it:

```bash
uv run python scripts/add_agent.py mcp_tools --name calendar
```

To adapt it, replace the tools in `service/server.py` (or point `MCP_SERVER_URL` at an MCP server you
already have) and rewrite the agent's instructions. Dates are a good fit for a tool: models are
unreliable at calendar arithmetic, and a tool makes it exact.
