# Supervisor / workers

A supervisor agent decides which specialized workers to call, in what order, and what to hand
each, then synthesizes the results.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

**Use it when** a task splits into specialized subtasks, workers need different tools,
instructions or output types, or you want a coordinator that makes the routing decision itself.

```
supervisor_agent → decides which worker to call, and what to hand it
  analyst_agent  → researches a question and returns key findings
  writer_agent   → turns material into clear prose
```

**What it shows**
- Delegation as tools on the supervisor (`delegate_to_analyst`, `delegate_to_writer`): the model
  chooses whether to call one worker, both, or neither, and passes the analyst's findings to the
  writer itself
- `usage=ctx.usage` so workers spend from the supervisor's shared budget
- One `USAGE_LIMITS` bounding the whole delegation tree
- The result has one step (the supervisor's); the workers ran inside it, so their calls are in
  `.all_messages()` and their spend is in `.usage`

**How it differs:** in `pipeline` the order is fixed by code; in `router` code picks one
specialist from a classification. Here the model decides, which is more flexible and less
predictable.

```bash
uv run python scripts/add_agent.py supervisor --name my_agent
```

To adapt it, replace the two workers with your own and describe in the supervisor's
instructions when each is the right call.
