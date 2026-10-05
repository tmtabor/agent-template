# Code mode

Let the model write Python that calls your tools, in a sandbox.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

**Use it when** a question needs many tool calls (loop over records, join two lookups, aggregate),
it needs exact arithmetic, which models get wrong when they add numbers in their head, and you'd
rather have one or two model round trips than dozens.

```
plain tool calling   list ids → get_expense × 10 → get_exchange_rate × 3 → add it up by hand
code mode            run_code( a loop that fetches, converts and sums, exactly )
```

**What it shows**

- **The `CodeMode` capability** (from `pydantic-ai-harness`) hides the agent's tools behind one
  `run_code` tool. The model writes Python that calls them as `await get_expense(expense_id=...)`;
  each call really runs your tool on the host, with your deps. The tools are ordinary `@agent.tool`
  functions, so any agent's tools can be used this way
- **A real sandbox.** The code runs in Monty, a minimal Python interpreter built for untrusted code,
  with no filesystem, environment, clock, network or subprocess. It is checked against your tools'
  signatures before it runs, and bounded by a time limit, a memory limit and a cap on tool calls per
  snippet (`SANDBOX_LIMITS`, `MAX_TOOL_CALLS`). A snippet that breaks a rule fails with an error the
  model reads and fixes; nothing happens on the host
- **Proved, not claimed.** The offline tests run real hostile code in the real sandbox (reading and
  writing files, the environment, the clock, a socket, a subprocess, an infinite loop, a memory bomb, a
  runaway tool loop) and check the *host*: no file created, no secret returned, exactly the capped
  number of tool calls made, the loop stopped at its time limit
- **Exact answers, checked.** The live tests compare the model's figures with totals worked out
  independently from the data (a total across five currencies; the employee with the most meal spend),
  and check `deps.calls`, a ledger of every tool call the code really made, to show the work was done
- **The payoff, measured:** dozens of host tool calls from a model that needed two or three requests
- A grounding check: an output validator rejects an answer whose `subject` isn't a real employee or
  expense id

```bash
uv run python scripts/add_agent.py code_mode --name expenses
```

This is the first example that needs a package of its own: `add_agent.py` installs
`pydantic-ai-harness[code-mode]` with `uv add`. It is pre-1.0 and its minor version tracks Pydantic
AI's (0.54 goes with 2.54), so upgrade the two together.

To adapt it, replace the expense data and the four tools with your own. Keep the tool signatures typed
and documented, because the model's code is written against them.
