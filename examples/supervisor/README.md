# Supervisor / workers

A supervisor agent decides which specialized worker to call, and synthesizes the results.

**Use it when** a task splits into specialized subtasks, workers need different tools,
instructions or output types, or a coordinator should manage routing and escalation.

```
supervisor_agent → decides which worker to call
  worker_agent_a → handles task type A
  worker_agent_b → handles task type B
```

**What it shows**
- Delegation as tools on the supervisor (`delegate_to_worker_a`)
- `usage=ctx.usage` so workers spend from the supervisor's shared budget
- One `USAGE_LIMITS` bounding the whole delegation tree

```bash
uv run python scripts/add_agent.py supervisor --name my_agent
```
