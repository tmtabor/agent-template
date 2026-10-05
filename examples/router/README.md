# Router

A cheap classifier picks a category, and plain code sends the input to the right specialist.

**Use it when** inputs fall into a known set of categories, each best handled by its own
agent, and you want routing that is predictable, testable and cheap.

```
classifier → category → SPECIALISTS[category] → answer
```

**How it differs from `supervisor`:** there, the LLM decides which worker to call by using
delegation tools. Here the model only *classifies*; a dictionary in your code does the
dispatch. There is no agentic loop to bound and the routing logic is ordinary Python.

**What it shows**
- Classification as a `Literal` output type: the model can only return a known category
- Dispatch in code (`SPECIALISTS[category]`), each specialist with its own instructions
- One `RunUsage` shared across the classifier and the specialist, so `USAGE_LIMITS` bounds
  the whole route
- Trace labels `<name>.classifier`, `<name>.billing`, … so each hop is identifiable

```bash
uv run python scripts/add_agent.py router --name support
```

Adapt it by changing `Category` and `SPECIALISTS`. The smoke tests drive `router_agent` (the
classifier); `examples/router/test_example.py` tests the dispatch itself.
