# Tool-calling agent

An agent whose tools reach external systems: the model decides which to call, and when.

Tools are ordinary Python functions you register on an agent. The model sees each tool's name, arguments and docstring, decides when a call would help, and the result goes back into the conversation so it can decide what to do next. The loop repeats until it has an answer. Most of what makes tools reliable is in how you write them: keep the interface simple, report errors in plain English the model can act on, and keep large payloads inside the tool and out of the context. This example is a lookup over Python release notes, with the backend behind the dependencies so you can swap in an API client or a database.

**Use it when**

- The agent has to read from or act on the outside world: an API, a database, files.
- What the model should do next depends on what a tool returned.
- You want the model to choose which tool to call, and when, and not follow a fixed sequence.

**Look elsewhere when**

- The tools already exist as an MCP server shared with other clients: [`mcp_tools`](../mcp_tools/).
- One question needs dozens of calls and exact arithmetic: [`code_mode`](../code_mode/).
- A tool can do something you can't undo: add [`human_in_the_loop`](../human_in_the_loop/).

**What it shows**
- A working tool, `python_release_notes`, over an in-memory table of Python releases. The data
  lives behind `ToolAgentDeps`, which is where an API client or database connection goes
- Simple tool interfaces, English error messages, large payloads held at the tool layer
- The three-outcome error convention in one tool: success, `ModelRetry` (a malformed version
  like `"latest"` or `"3.13.1"` — the model can fix it) and `ToolFailed` (an unknown version —
  nothing to find, so no retry budget is spent)
- `agent/tools/example.py` for the same convention in a standalone tool

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

```bash
uv run python scripts/add_agent.py tool_calling --name my_agent
```

To adapt it, replace `RELEASES` and `python_release_notes` with your own lookup, and keep the
three outcomes.
