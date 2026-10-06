# Fan-out / fan-in

Run independent workers in parallel, then combine what they found.

Fan-out sends the same task to several workers at once, each with a different angle (here benefits, drawbacks and risks), and fan-in combines what they return into one answer. The parallelism is `asyncio.gather` in your code, not a model decision. A worker that fails doesn't sink the run: the others' work is kept, the failure is reported, and the answer is built from what succeeded.

**Use it when**

- The subtasks are independent: different perspectives, sources or chunks of a document.
- Wall-clock time matters.
- One worker failing shouldn't sink the whole answer.

**Look elsewhere when**

- Each step needs the one before it: [`pipeline`](../pipeline/).
- Which workers run depends on the input: [`router`](../router/) or [`planner_executor`](../planner_executor/).

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

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

```bash
uv run python scripts/add_agent.py fan_out --name analysis
```

`run_fan_out` returns a `RunResult`: `.output` is the summary and which perspectives were used or
failed, and `.steps` holds the workers that succeeded (in completion order) and then the aggregator.

Adapt it by changing `PERSPECTIVES` or replacing them with your own subtasks.
`examples/fan_out/test_example.py` tests the parallelism and the failure cases.
