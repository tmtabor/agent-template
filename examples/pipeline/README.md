# Pipeline

Fixed sequential steps, each one's output feeding the next. Also called a prompt chain.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

**Use it when** a task decomposes into stages that always run in the same order, each stage
is more reliable as its own focused prompt, and you want to check intermediate results and
stop early.

```
outline → draft → polish     (code decides the order; the model never does)
```

**What it shows**
- Each step is its own agent with a typed output (`Outline`, `Draft`, `Polished`)
- A **gate** between steps: plain code checks the previous output and fails fast
  (`EmptyOutlineError`), so later steps never spend tokens on nothing
- One `RunUsage` shared by every step, so `USAGE_LIMITS` bounds the whole chain
- Trace labels `<name>.outline`, `<name>.draft`, `<name>.polish`

```bash
uv run python scripts/add_agent.py pipeline --name article
```

`run_pipeline` returns a `RunResult`: `.output` is the piece, `.steps` the three steps in order,
and `.usage` the total across all of them.

Adapt it by changing the steps and what each one returns. The generic smoke test runs the whole
chain offline; `examples/pipeline/test_example.py` tests the gate and the shared budget.
