# Supervisor / workers

A supervisor agent decides which specialized workers to call, in what order, and what to hand each, then synthesizes the results.

A supervisor is an agent whose tools are other agents. Each worker has its own instructions, tools and output type. The supervisor sees them as delegation tools and decides, one turn at a time, which to call, in what order, and what to give each. It can call one worker, several, or none, and it writes the final answer from what they return. Nothing about the sequence is decided in advance. That is what makes it flexible, and also what makes it the least predictable of the multi-agent patterns.

**Use it when**

- A task splits into specialised subtasks.
- Workers need different tools, instructions or output types.
- You want a coordinator that makes the routing decision itself, and you can't know the steps in advance.

**Look elsewhere when**

- You can list the steps today: [`pipeline`](../pipeline/).
- The input decides which specialist runs: [`router`](../router/).
- You want the plan checked before anything runs: [`planner_executor`](../planner_executor/).

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

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

```bash
uv run python scripts/add_agent.py supervisor --name my_agent
```

To adapt it, replace the two workers with your own and describe in the supervisor's
instructions when each is the right call.
