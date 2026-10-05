# Pipeline

Fixed sequential steps, each one's output feeding the next. Also called a prompt chain.

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

Adapt it by changing the steps and what each one returns. The smoke tests drive
`outline_agent` (the first step); `examples/pipeline/test_example.py` tests the chain itself.
