# MCP tools

Give an agent the tools of a Model Context Protocol (MCP) server that runs as its own service.

The Model Context Protocol (MCP) is a standard way for a program to offer tools to AI agents. Instead of writing the tools into your agent, you point the agent at an MCP server: it connects, asks what tools the server has, and offers them to the model like any other. When the model calls one, the call goes over the network to the server and the result comes back. The server is its own process, so it can be written in any language, run anywhere, and be shared by this agent, an IDE and any other client. Here it runs as a Docker service.

**Use it when**

- The tools already exist as an MCP server, yours or someone else's.
- One tool implementation should serve several clients: this agent, an IDE, another application.
- Tools should be discovered at run time and not hard-coded into the agent.

**Look elsewhere when**

- The tools are plain functions that only this agent uses: [`tool_calling`](../tool_calling/) is simpler, with nothing to run beside it.

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
  port 8000 on this machine, which the Docker service does not use: it publishes on a random free port) feeds a toolset the agent builds per run (`@agent.toolset`), so the same agent
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

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

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
