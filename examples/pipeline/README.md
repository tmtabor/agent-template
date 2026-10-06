# Pipeline

Fixed sequential steps, each one's output feeding the next. Also called a prompt chain.

A pipeline breaks a task into stages that always run in the same order, each its own agent with a focused prompt and a typed output: here an outline, then a draft written from it, then a polished version. Code, not the model, decides the order, so the control flow is ordinary Python that is cheap to test and to bound. Between stages, code can check the previous output and stop early, so later stages never spend tokens on nothing.

**Use it when**

- A task decomposes into stages that always run in the same order.
- Each stage is more reliable as its own focused prompt than inside one long prompt.
- You want to check intermediate results and stop early.

**Look elsewhere when**

- The steps vary by input: [`router`](../router/) or [`planner_executor`](../planner_executor/).
- The stages don't depend on each other and could run together: [`fan_out`](../fan_out/).

```
outline → draft → polish     (code decides the order; the model never does)
```

**What it shows**
- Each step is its own agent with a typed output (`Outline`, `Draft`, `Polished`)
- A **gate** between steps: plain code checks the previous output and fails fast
  (`EmptyOutlineError`), so later steps never spend tokens on nothing
- One `RunUsage` shared by every step, so `USAGE_LIMITS` bounds the whole chain
- Trace labels `<name>.outline`, `<name>.draft`, `<name>.polish`

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

```bash
uv run python scripts/add_agent.py pipeline --name article
```

`run_pipeline` returns a `RunResult`: `.output` is the piece, `.steps` the three steps in order,
and `.usage` the total across all of them.

Adapt it by changing the steps and what each one returns. The generic smoke test runs the whole
chain offline; `examples/pipeline/test_example.py` tests the gate and the shared budget.
