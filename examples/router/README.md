# Router

A cheap classifier picks a category, and plain code sends the input to the right specialist.

A router handles different kinds of input differently. A small classifier agent reads the input and returns one category from a fixed list (its output type allows nothing else). Plain code then looks the category up in a dictionary and hands the input to that category's specialist agent. The model decides only what kind of thing this is; what happens next is ordinary Python, so it is predictable, easy to test and cheap, and there is no agent loop to bound.

**Use it when**

- Inputs fall into a known set of categories.
- Each category is best handled by its own agent, with its own instructions, tools or tone.
- You want routing that is predictable, testable and cheap.

**Look elsewhere when**

- The categories aren't known in advance, or one request needs several specialists: [`supervisor`](../supervisor/).
- Every input gets the same handling: [`single`](../single/).

```
classifier → category → SPECIALISTS[category] → answer
```

**What it shows**
- Classification as a `Literal` output type: the model can only return a known category
- Dispatch in code (`SPECIALISTS[category]`), each specialist with its own instructions
- One `RunUsage` shared across the classifier and the specialist, so `USAGE_LIMITS` bounds
  the whole route
- Trace labels `<name>.classifier`, `<name>.billing`, … so each hop is identifiable

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

```bash
uv run python scripts/add_agent.py router --name support
```

`run_router` returns a `RunResult`: `.output` is the answer and its category, and `.steps` records
the route taken (the classifier, then that category's specialist).

Adapt it by changing `Category` and `SPECIALISTS`. `examples/router/test_example.py` tests the
dispatch and the shared budget.
