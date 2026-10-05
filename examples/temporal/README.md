# Temporal

Run an agent as a durable Temporal workflow: a failing tool is retried, and a worker that dies mid-run is replaced, without asking the model again for anything it already answered.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.
It is the model's view, in which the carrier never failed: the retry is what the tests and the server's history show.

**Use it when** a run is long enough, or touches enough flaky systems (a carrier's API, a payment
provider, a slow database), that a crash or an outage partway through would otherwise mean starting
over and paying for the model calls again; or when you want to start a run, leave, and come back to it.

```
your code ── start workflow ─▶  Temporal server  ◀── polls ──  worker
                                (its own container)            runs the agent loop (workflow),
                                keeps the history              every model request and every tool
                                                               call (activities)
```

**What it shows**

- **Durability by one capability.** `TemporalDurability()` in the agent's `capabilities` turns every
  model request and tool call into a Temporal *activity* and the agent loop into a *workflow*. The
  agent, its tools and its output type are written exactly as in a plain agent
- **A failing tool is retried, and the model never knows.** The shipping carrier is down the first
  time it is asked about each shipment. Temporal retries the call under `RETRY_POLICY` (up to 5
  attempts, backing off); the model sees only the answer. The tests check the server's own record:
  the model-request activity ran once per request, and the carrier call's recorded attempt is 2
- **A worker that dies is replaced.** Start a run, kill the worker mid-tool-call (the tests do both
  a tidy shutdown and a `SIGKILL` of a separate worker process), start another, and the run finishes.
  The model request that had already finished is *not* run again: the new worker replays the history
- **A run that can't hang.** A bug in workflow code does not fail the run: Temporal keeps retrying
  the failing step, and the caller waits (one mistyped attribute did this while building the example).
  `run_order_desk` sets an execution timeout (`RUN_TIMEOUT`) so a run that never finishes raises
  `RunTimedOut` instead; the tests check it with a model call that never returns
- **A server that isn't there:** `TemporalUnavailable` says where it looked and how to start it
- **The same `RunResult`.** The workflow returns an `AgentRunResult` (its return annotation is what
  makes the client receive a real one), so `.output`, `.usage` and the messages are as for any agent
- **Tested against the real server.** There is no offline Temporal: its test server downloads a
  binary at run time. So the tests need the Docker service and are skipped without it; the release
  check starts the service, runs them (with the model replaced by `TestModel`) and then the live tests

## Running it

```bash
docker compose -f examples/temporal/service/docker-compose.yml up -d --wait
export TEMPORAL_ADDRESS=$(docker compose -f examples/temporal/service/docker-compose.yml port temporal 7233)
uv run --with "temporalio>=1.34,<2" python -m examples.temporal.agent
docker compose -f examples/temporal/service/docker-compose.yml down
```

Start it with `python -m`, not by file path: Temporal's sandbox imports the workflow's module by
name, so a workflow cannot live in `__main__`.

To use it in your project, `add_agent.py` copies the agent into `agent/agents/`, the service into
`services/<name>/`, and installs `temporalio`:

```bash
uv run python scripts/add_agent.py temporal --name orders
```

## Putting the worker in its own process

`run_order_desk` runs a worker *inside the calling process*, which keeps the example in one file. In
production the worker is a separate, long-running process, so that a crash of your web server does not
stop the work and a crash of a worker does not stop the caller. That process is three lines:

```python
client = await connect(os.environ["TEMPORAL_ADDRESS"])
await make_worker(client).run()  # polls the task queue until you stop it
```

The tests run exactly that in a subprocess and `SIGKILL` it. Note that the server only learns a worker
is gone when the activity's timeout (`ACTIVITY_CONFIG`, 30 s) passes, so a hard kill delays the retry by
about that long; a tidy shutdown does not.

## Things worth knowing

- **Tools and deps run in activities, so they are serialized.** `DeskDeps` crosses into every activity,
  and a tool's arguments and results cross as JSON. State kept in module-level objects (like the
  carrier's call ledger here) is visible only because the demo's worker is in the same process
- **Spans:** `LogfirePlugin` sends Temporal's own spans (the workflow and each activity) to Logfire.
  Pydantic AI's `invoke_agent` span is not among them, so the span-based checks used by the other
  examples cannot see this agent run; the workflow's history on the server is the record
- **One workflow per agent.** Two workflows that list the same agent register the same activities and
  the worker refuses to start

To adapt it, replace the tools and `Carrier` with your own, give them the retry behaviour you want in
`RETRY_POLICY` (a tool whose failure retrying cannot fix should raise a Temporal `ApplicationError`
with `non_retryable=True`, which is tried once and fails the run), and rewrite the instructions.
