# Fan-out / fan-in

Run independent workers in parallel, then combine what they found.

**Use it when** subtasks are independent (different perspectives, sources or chunks of a
document), wall-clock time matters, or one worker failing shouldn't sink the whole answer.

```
topic ─┬→ worker (benefits)  ─┐
       ├→ worker (drawbacks) ─┼→ aggregator → answer
       └→ worker (risks)     ─┘
```

**What it shows**
- The fan-out is `asyncio.gather` — ordinary Python, not an LLM decision
- `return_exceptions=True`, so one failed worker doesn't discard its siblings' paid-for work;
  failures are reported in the output (`perspectives_failed`), and
  `AllWorkersFailedError` is raised only if nothing succeeded
- One `RunUsage` shared across the parallel runs, so `USAGE_LIMITS` bounds all of them
- Trace labels `<name>.worker` and `<name>.aggregator`

```bash
uv run python scripts/add_agent.py fan_out --name analysis
```

Adapt it by changing `PERSPECTIVES` or replacing them with your own subtasks. The smoke tests
drive `worker_agent`; `examples/fan_out/test_example.py` tests the fan-out and the failure cases.
