# Tool-calling agent

An agent whose tools reach external systems (APIs, databases, files); the model decides
which to call and when.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

**Use it when** the agent needs to act on or read from the outside world and tool results
should inform its next step.

**What it shows**
- A working tool, `python_release_notes`, over an in-memory table of Python releases. The data
  lives behind `ToolAgentDeps`, which is where an API client or database connection goes
- Simple tool interfaces, English error messages, large payloads held at the tool layer
- The three-outcome error convention in one tool: success, `ModelRetry` (a malformed version
  like `"latest"` or `"3.13.1"` — the model can fix it) and `ToolFailed` (an unknown version —
  nothing to find, so no retry budget is spent)
- `agent/tools/example.py` for the same convention in a standalone tool

```bash
uv run python scripts/add_agent.py tool_calling --name my_agent
```

To adapt it, replace `RELEASES` and `python_release_notes` with your own lookup, and keep the
three outcomes.
