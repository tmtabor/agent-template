# Tool-calling agent

An agent whose tools reach external systems (APIs, databases, files); the model decides
which to call and when.

**Use it when** the agent needs to act on or read from the outside world and tool results
should inform its next step.

**What it shows**
- Simple tool interfaces, English error messages, large payloads held at the tool layer
- The three-outcome error convention: `ModelRetry`, `ToolFailed`, or re-raise
- `agent/tools/example.py` for the fuller tool pattern

```bash
uv run python scripts/add_agent.py tool_calling --name my_agent
```
