# Single agent

One agent handles the whole task: the simplest pattern, and the one to start from.

A single agent takes a request and answers it, using a prompt and a typed output you define. There is no coordination, no routing and no external calls unless you add them, which makes it the easiest pattern to reason about, test and debug. This example is a complete, working version: a structured output type, instructions in a prompt file, usage limits, and commented recipes for what you will usually add next (tools, dynamic instructions, multi-turn history).

**Use it when**

- One agent can do the whole job with one prompt.
- Nothing needs to be specialised, delegated or run in parallel.
- You want the lowest complexity and the easiest thing to test.
- You are not sure which pattern you need: start here and add one when a real run shows what is missing.

**Look elsewhere when**

- The agent needs facts it can't know, or must act in other systems: [`tool_calling`](../tool_calling/).
- The task is really several tasks with different prompts: [`pipeline`](../pipeline/), [`router`](../router/) or [`supervisor`](../supervisor/).
- It must remember earlier turns: [`conversation`](../conversation/).

**What it shows**
- A structured output type (`AgentOutput`) and an injectable deps dataclass (`AgentDeps`)
- Instructions loaded from a prompt file (`prompts/single.txt`)
- `USAGE_LIMITS` as a guardrail on every run, and `RaiseContentFilterError`
- Commented recipes for tools, dynamic instructions and multi-turn history
- `test_example.py`: how to unit-test an agent with `TestModel`

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

```bash
uv run python scripts/add_agent.py single --name my_agent
```
