# Example agent library — plan

Status: steps 1-7 are implemented and verified (7a Monty, 7b Temporal), including the services
machinery. **Work still required** is listed under "Still open" below: enabling GitHub Pages, two
deferred patterns, and one optional improvement. Date: 2026-10-05.

## Still open

These need work; everything else in this plan is done.

1. **Enable GitHub Pages (needs the repo owner).** The docs site and its deploy workflow
   (`.github/workflows/docs.yml`) are built, but the site is not live until Settings -> Pages ->
   Source is set to "GitHub Actions". Nothing in the repo can do this.
2. **Router classifier output retries (optional, skipped for now).** The router agent sets no `retries=`
   (so it uses Pydantic AI's default), where `extraction` and `guardrails` use `retries={"output": 2}`.
   No failure has been observed; the earlier note that this was "considered during step 6" has no
   record behind it. Skipped by decision, not forgotten.

Done since step 7: the **planner-executor** example and **vector-backed retrieval** (see their notes below).

## Goals

1. A browsable library of example agents built on the template, showing common
   agent patterns.
2. Easy to start from: a user picks one example and works from it.
3. Linked from the README and published as a docs site (GitHub Pages).
4. Reusable as an ad hoc pre-release test: every example is verified to run
   before a release.

The three existing stubs (`single`, `supervisor`, `tool_calling`) are part of
the library and are its first three entries.

## Decisions

| Topic | Decision |
|---|---|
| Location | Top-level `examples/`, outside `agent/agents/`, so selection scripts never delete or rewire them. |
| Source of truth | The stubs move out of `agent/agents/` into `examples/`. `add_agent.py` copies from there. |
| Docs tool | MkDocs with the Material theme, deployed to GitHub Pages. |
| Dependencies | Example dependencies are never in the root `pyproject.toml` or `uv.lock`. Each example declares its own. |
| Agent model | The template starts with **no agents**. There is no "primary" agent and no canonical `run_agent` / `AgentOutput` / `AgentDeps` / `agent` re-export. Each agent is its own module under `agent/agents/`, imported directly. Run `add_agent.py` once per agent; each can use a different pattern. |
| Scripts | One script, `scripts/add_agent.py`, replaces both `choose_pattern.py` and the old `add_agent.py`. Users pick from a menu of patterns, including a `blank` example. No `use_example.py`. |

## Layout

```
examples/
├── README.md                # generated index: pattern, what it shows, deps, cost
└── <name>/
    ├── __init__.py          # makes the example importable in place (tests)
    ├── agent.py             # same conventions as agent/agents/*.py
    ├── prompts/*.txt        # named <example>.txt or <example>_<role>.txt
    ├── example.toml         # metadata (schema below)
    ├── README.md            # when to use, architecture, how to adapt
    ├── sample_run.md        # committed real transcript (input, tool calls, output, cost)
    ├── test_example.py      # optional example-specific assertions
    └── docker-compose.yml   # optional, for examples that need services
docs/                        # MkDocs source; docs/plans/ holds records like this file
mkdocs.yml
```

Examples import `agent.config` and `agent.logging`; they are not standalone
projects.

## `example.toml` schema

```toml
title = "Supervisor / workers"
pattern = "supervisor"            # category used for the index and docs nav
summary = "One-line description."
smoke_input = "Input for the release check."
expected_tools = ["delegate_to_analyst"]   # tools that must be called in smoke runs
cost_budget_usd = 0.10            # live smoke run must stay under this
dependencies = []                 # PEP 508 requirements beyond the template's own
env = []                          # extra environment variables required
services = []                    # e.g. ["temporal"]; needs docker-compose.yml

[entrypoint]                      # where tests and the release check find the example's API
deps = "SharedDeps"
run = "run_supervisor"            # async (user_input) -> RunResult, see "Run results"

[smoke.supervisor_agent]          # per-agent TestModel config for offline smoke tests
call_tools = ["delegate_to_analyst"]   # (`output = {...}` is also accepted)
```

(`expected_tools` and `cost_budget_usd` belong to the live tier, step 4. The key set built so far
is listed under "Implementation notes".)

`[entrypoint]` replaces the alias mapping that `choose_pattern.py` hard-coded.
Nothing is renamed or re-exported: an added agent keeps the example's own
symbol names, and lives in its own module, so several agents never collide.

## `scripts/add_agent.py`

The user starts with no agents. Each time they want one they run
`add_agent.py`, pick a pattern (including `blank`) from a menu built from the
`example.toml` titles and summaries, and get an agent. Three agents means three
runs, each with its own pattern.

```bash
uv run python scripts/add_agent.py                     # interactive menu, asks for a name
uv run python scripts/add_agent.py supervisor --name triage
uv run python scripts/add_agent.py router --name inbox
uv run python scripts/add_agent.py blank --name newsletter
uv run python scripts/add_agent.py --prune
```

- **Copies** the example's module to `agent/agents/<name>.py` and its prompts to
  `agent/prompts/`, with prompt paths rewritten to match. `--name` defaults to
  the example's own name. The same example can be added twice under different
  names. It refuses to overwrite an existing agent.
- **Scaffolds tests:** a smoke test `tests/test_agents_<name>.py`, plus an eval
  starter under `evals/` for the agent. Both are generated from the example's
  own test and `smoke_input`, so every agent arrives with its checks.
- **`blank`** is the old `add_agent.py` scaffold as an ordinary example; its
  symbols are templated on `--name`. Other examples keep their symbols.
- **Dependencies:** runs `uv add` for the declared `dependencies` and prints the
  required `env` vars and `services`.
- **`agent/agents/__init__.py`** stays an empty package marker. Agents are
  imported as `from agent.agents.<name> import ...`.
- **`--prune`:** remove every example except `blank` (kept so agents can still be
  added), plus `docs/`, `mkdocs.yml`, the Pages workflow, the `docs` dependency
  group, and the example tests, leaving a lean project.
  Shows what it will delete and requires confirmation or `--yes`.

This replaces both `choose_pattern.py` (removed, no shim) and the old
`add_agent.py`. It is a documented, breaking change: update the README,
`AGENTS.md`, tests and docs, and record it in the changelog under Changed.

## Fresh-clone behavior

A fresh clone contains no agents. `uv run pytest` runs the tests that do not
need one (config, logging, tools, content filter, cost limit, event loop); the
example tests run as part of the offline tier. Because nothing is materialized,
there is no copy to drift from `examples/`, and no drift check.

Template code that used the canonical agent must change:

- `tests/test_safety_net.py` and `tests/test_example.py` currently import
  `agent` and `AgentDeps` from `agent.agents`. They are rewritten to build their
  own minimal agent, or to run against `examples/single`, so they need no
  chosen agent.
- `evals/test_pass_fail.py` and `evals/test_llm_judge.py` import `run_agent`.
  They become the eval starter that `add_agent.py` generates per agent;
  `evals/judge.py` and the shared fixtures stay as helpers.
- The `agent-web-ui` skill imports `agent`, `AgentDeps` and `USAGE_LIMITS` from
  `agent.agents`. It is updated to take the agent module to serve (e.g.
  `agent.agents.triage`) instead of assuming one canonical agent.
- README and `AGENTS.md` drop the "canonical names" contract and describe the
  `add_agent.py` workflow instead.

## Dependencies

- The root `pyproject.toml` and `uv.lock` never mention example dependencies.
  The only addition is a `docs` dependency group (mkdocs-material plus the
  gen-files plugin), kept out of `dev`.
- Each example's isolated test run installs its declared dependencies:
  `uv run --with <dep> ... pytest examples/<name>`. Two examples never share an
  environment, so they cannot conflict, and an undeclared dependency fails.
- The default `uv run pytest` collects only examples with no extra dependencies.
  Others are skipped with an explicit reason; no example imports heavy
  dependencies at collection time in the root run.
- The docs build never imports examples. Pages render source as text, so no
  `mkdocstrings` on example code and no example dependencies in the docs build.
- Services (Temporal, databases) are declared in `example.toml` and started from
  the example's `docker-compose.yml` by the release check. If Docker is
  unavailable the example is reported as unverified, not passed.

## Testing

1. **Offline tier, every PR.** Parametrized over discovered `example.toml`
   files. Each example is imported and run under `TestModel`, like
   `tests/test_stubs.py` today. It also runs `add_agent.py` into a temporary
   copy of the repo for each example and runs the generated tests, so the
   script and its scaffolding are exercised too. Also checks: required files and metadata exist;
   the `[entrypoint]` names resolve; every `dependencies` entry parses. The conftest safety net is extended to cover `examples/`.
   Needs no API key, so the existing CI job covers it.
2. **Live tier, before release.** `scripts/release_check.py` runs each example's
   `smoke_input` against the real model in an isolated environment. Checks: the
   output validates, `expected_tools` were called, and cost stays within
   `cost_budget_usd`. It also refreshes each `sample_run.md`. Run it by hand, locally, before a
   release; it is deliberately not part of CI (it spends money and needs a key).
3. `scripts/record_example.py <name>` regenerates one example's `sample_run.md`.

## Pattern roadmap

Required (the three stubs): single, tool-calling, supervisor/workers. Plus
`blank`, the empty scaffold.

Then, in priority order:

| Pattern | Shows | Extra dependencies |
|---|---|---|
| Structured extraction | Unstructured text to a validated schema, with retries | none |
| Router | Cheap classifier dispatches to specialists; routing in code, not by the LLM | none |
| Prompt chain / pipeline | Fixed sequential steps, each output feeding the next | none |
| Parallel fan-out | `asyncio.gather` over workers, then an aggregator | none |
| Evaluator–optimizer | Generator and critic loop with an iteration cap | none |
| RAG / retrieval | Retrieval tool over documents, with citations; by meaning, in Chroma as a service (built: `rag`) | `chromadb-client`; a Chroma server (`services = ["chroma"]`) |
| Human-in-the-loop | Deferred tools requiring approval before risky actions | none |
| Conversational with memory | Message history across turns, plus streaming | none |
| Guardrails | Input/output validation, content-filter handling, cost limits | none |
| MCP tools | Consuming an MCP server's tools, running as a Docker service (built: `mcp_tools`) | none for the agent; `fastmcp` for the server's tests |

Heavier examples, built in step 7 (they need extra dependencies or services and
exercise the isolated-environment and `services` machinery):

| Pattern | Shows | Extra dependencies / services |
|---|---|---|
| Code execution (Monty) | The model writes Python that runs in a sandboxed interpreter, with only the tools and inputs the example exposes (built: `code_mode`) | `pydantic-ai-harness[code-mode]` (which brings `pydantic-monty`) |
| Durable workflow (Temporal) | An agent run as a durable, resumable Temporal workflow: retries and crash recovery (built: `temporal`) | `temporalio`; a Temporal server (`services = ["temporal"]`, started from the example's `docker-compose.yml`) |

Built after step 7: planner-executor (`planner_executor`) and vector-DB-backed retrieval (`rag` itself, replacing its keyword search). Nothing in the pattern roadmap is deferred any more.

## Trace labels

An agent's `name=` labels its run span in Logfire, so it should be the name the
user chose in `add_agent.py`, not the example's. The fix needs no source
rewriting: labels are derived from the module name.

- Add `agent_label(module_name)` to `agent/logging.py`. For a copied agent
  (`agent.agents.triage`) it returns the last segment, `triage`. For an example
  run in place (`examples.supervisor.agent`) it returns the example's directory
  name, `supervisor`.
- Every example sets `LABEL = agent_label(__name__)` and uses it:
  `name=LABEL` for the main agent and `name=f"{LABEL}.worker_a"` for helpers, so
  traces group under the user's agent name and workers read as `triage.worker_a`.
  The same example added twice therefore gets two distinct labels.
- `add_agent.py` needs no change for this, and `blank`'s `name="blank"` moves to
  the same helper (its renaming of `blank` symbols is then only for identifiers).
- Test in `tests/test_add_agent.py`: after adding an example as `triage`, every
  `Agent` in the copied module has a `.name` equal to `triage` or starting with
  `triage.`. This also guards every new example.

## Run results (step 3)

**Problem.** Every `run_*` helper returns only the validated output and discards what
Pydantic AI already computed: usage, messages, per-step detail. The orchestrating examples
build a shared `RunUsage` and throw it away; the web-UI skill had to bypass `run_agent()`
because the helper hides the result; the generic tests cannot see what a flow did; and
`sample_run.md` transcripts, cost reporting and the Temporal example all need that
information. Recording `Agent.run` calls in the tests was considered and rejected: it works
around the contract instead of fixing it.

**Decision (option A): one uniform result type for every example.** `run_*` always returns
the same small dataclass, defined once in `agent/runs.py` (`usage` is a property on Pydantic AI's
native result in 2.54, so it is a field here too):

```python
@dataclass
class Step:
    agent: str                  # the agent's label (see "Trace labels")
    result: AgentRunResult      # the native Pydantic AI result, untouched

@dataclass
class RunResult(Generic[OutputT]):
    output: OutputT             # the run's own output; for flows, built in code from the steps
    steps: list[Step]           # every agent run, in order (a list: labels repeat)
    usage: RunUsage             # total across steps; stored, not summed (steps share one object)
    def all_messages(self) -> list[ModelMessage]
```

- A single agent is a one-step run; callers always write `(await run_x(...)).output`, and
  anyone who wants the native object takes `.steps[0].result`. Moving from `single` to
  `router` never changes a call site.
- The type exists because in `router`, `pipeline` and `fan_out` the output is synthesized in
  code from several steps and is no single step's output. Everything else is derivable.
- A small optional `Flow` helper in the same module owns the shared `RunUsage` and limits and
  records each step (`await flow.run(agent, prompt, deps=deps)`, then `flow.finish(output)`),
  replacing the `usage=..., usage_limits=...` boilerplate repeated across the examples. It is
  a convenience for building results, not part of the contract.

**Manifest.** Smoke configuration becomes per agent (a `call_tools` list and an `output` table), keyed by the agent's variable name, and
replaces `smoke_tools`, `smoke_output` and `[entrypoint] agent` (which only ever meant "the
agent the tests happen to drive"). `[entrypoint]` keeps `deps` and `run`.

```toml
[smoke.supervisor_agent]
call_tools = ["delegate_to_analyst"]

[smoke.extraction_agent]
output = { name = "Ada Lovelace", email = "ada@example.com" }
```

Agents without an entry get the default: a `TestModel` that calls no tools.

**Tests.**
- The generic smoke test calls `run(smoke_input)` with each agent's smoke model applied, so
  the whole flow runs offline for every example. It asserts on the `RunResult`: at least one
  step, every step's label carries the example's name, the opted-in tools were called
  somewhere across the steps, and `usage().requests` is within the example's `USAGE_LIMITS`.
- The content-filter test checks every agent in the module directly, not one per example.
- The generated `tests/test_agents_<name>.py` does the same through the copied agent's `run`.
- The cost-limit tests use `run` where they can; the enforcement test seeds usage and stays on
  `agent.run`.

**What changes.** `agent/runs.py` (+ tests); all nine examples' `run_*` helpers and their
`test_example.py`; `example_manifest.py`; `tests/examples_support.py`; the generic tests;
`add_agent.py`'s generated smoke test and eval starter; `evals/helpers.py` (reads `.output`);
README, `AGENTS.md`, the web-UI skill and the changelog.

**Breaking change.** `run_agent()` and the other helpers change return type relative to 0.2.0.
The unreleased changelog already carries breaking changes, and there are no production users
of the example library yet, which is why it is done now. Add an Upgrade note.

**Open items, as settled.**
- Resolved in step 6: `run_chat(..., history=)` takes message history, and `Flow.run` accepts
  `prompt=None` plus `message_history=` / `deferred_tool_results=` for resumed runs. The web-UI skill
  still calls `agent.run()` directly.
- The supervisor's workers stay **inside** the supervisor's single step (usage is total either
  way), which keeps the example teaching the standard `usage=ctx.usage` delegation pattern.
- Temporal (step 7b) did **not** need a serializable form of the result: a workflow annotated
  `-> AgentRunResult[Output]` hands the client a real `AgentRunResult`, so `RunResult` is unchanged.

## Docs site

- MkDocs Material, `mkdocs.yml` at the repo root, source in `docs/`.
- Pages for each example are generated from `example.toml`, the README and
  `sample_run.md` using `mkdocs-gen-files`; example source is shown as text.
- Nav: Getting started, Configuration, Patterns (one page per example), Reference.
- Deployed by a GitHub Pages workflow. The root README links to it and to
  `examples/README.md`.

## Implementation order

1. **Foundation.** Move the three stubs into `examples/` and delete them from
   `agent/agents/`, leaving an empty package; define the `example.toml` schema
   and loader; replace `choose_pattern.py` and the old `add_agent.py` with one
   `add_agent.py` (menu, `--name`, test and eval scaffolding, `--prune`,
   dependency install) and add the `blank` example; add the offline parametrized
   test and extend the conftest safety net; rework the canonical-name tests,
   evals and the web-UI skill as described under Fresh-clone behavior; update
   README, `AGENTS.md` and the changelog.
2. **Trace labels, then first new examples.** First add `agent_label(__name__)`
   (see "Trace labels") and switch the existing examples to it; then write
   extraction, router, pipeline, fan-out and evaluator–optimizer, each using it,
   with a README (the `sample_run.md` files wait for step 4's recorder).
3. **Uniform run results.** Replace "`run_*` returns only the output" with the `RunResult`
   contract described under "Run results": `agent/runs.py`, every example's run helper, the
   per-agent `[smoke]` manifest tables, the generic and generated tests, evals, docs and the
   changelog. Done when the generic smoke test drives each example's whole flow through
   `run` and asserts on the returned steps.
4. **Live verification.** `release_check.py`, `record_example.py` (which builds
   `sample_run.md` from a `RunResult`), the isolated per-example runs and the coverage gate, all run
   manually and locally (no CI job). Commit the `sample_run.md` files here.
5. **Docs site.** MkDocs Material config, gen-files generation, Pages workflow,
   README links.
6. **Remaining roadmap examples** (done): RAG/retrieval, human-in-the-loop, conversation with
   memory and streaming, guardrails, and MCP tools. See "Implementation notes (step 6)".
7. **Monty and Temporal examples** (done: 7a `code_mode`, 7b `temporal`). `mcp_tools` already proved the `dependencies` machinery (step 6);
   these two add the next hard cases:
   - **Monty (code execution):** `dependencies` in `example.toml`; tests skip in the
     root environment and run in the example's isolated one. Decide how the sandbox's
     limits (time, memory, allowed calls) are shown and tested, and that it never runs
     under the offline `TestModel` tier with real code execution unless that is safe.
   - **Temporal (durable workflow):** the first example with `services`. Needs a
     `docker-compose.yml`, release-check logic to start and stop the server, a clear
     "unverified (no Docker)" result when it can't, and a README on running a worker
     alongside the agent. Offline tests use Temporal's in-process test environment if
     it exists, otherwise they are limited to import and wiring checks.
   Temporal is the first example with `services`, so it proves that half of the machinery;
   expect small fixes to the manifest schema and release check.

## Risks and open items

- `[entrypoint]` must be accurate: the smoke tests and release check rely on it
  to find each example's agent. The offline test resolves the names.
- `--prune` is destructive; it must show what it will delete and require
  confirmation or `--yes`.
- Monty and Temporal were the least certain examples. Resolved in step 7: their package names, versions
  and integration points were checked against the installed docs and code, and the plan did change (see
  the 7a and 7b notes).
- Each example's live smoke run costs money. Budgets are enforced per example,
  and the release check should report total spend.
- `sample_run.md` transcripts can go stale between releases; regenerating them
  in the release check mitigates this.
- Dropping the canonical agent and renaming `choose_pattern.py` breaks anyone
  who imports `run_agent` / `AgentOutput` from `agent.agents` or follows the
  documented workflow; covered by the changelog entry.
- Copying an example under a new name must rewrite its prompt paths correctly;
  the temp-repo test of `add_agent.py` guards this.

## Implementation notes (step 6, as built)

Five examples, each held to step 4's standard: offline tests of every branch, real-model live tests
asserting behavior and that every agent ran, a recorded run, and 100% line coverage.

- **`rag`:** an in-memory knowledge base of *invented* store policies (a model can't answer from
  memory, so a correct answer proves retrieval), keyword retrieval, and an output validator that
  rejects any cited source the model didn't actually retrieve (`RagDeps.retrieved`). Live: grounded
  answers with real citations, a two-part question drawing on two passages, and "I couldn't find
  that" with empty sources for something uncovered.
- **`human_in_the_loop`:** a refund tool with three outcomes: small refunds run, larger ones raise
  `ApprovalRequired` (the run pauses and returns `DeferredToolRequests`; `run_refunds` asks a
  pluggable approver and resumes the same conversation), and impossible ones are rejected by
  `args_validator` *before* anyone is asked. `deps.refunds` is the ground truth, and an output
  validator rejects a claim the ledger contradicts. Live tests check the ledger, not the model's
  words. They found the model saying "I have submitted the request" after a denial (nothing was
  submitted); the prompt now forbids it and a live test guards it.
- **`conversation`:** message history across turns, a turn-based window (`ProcessHistory` with a
  `RunContext`-aware processor reading `max_turns` from deps, cutting only at turn boundaries so a
  tool call stays with its result), and streaming. `stream_text` merges chunks arriving within 100 ms
  by default (`debounce_by`), which made streaming timing-dependent; it is set to `None`. Live:
  remembers across turns, genuinely forgets a turn outside the window, streams real chunks. This
  resolves step 3's open item: `run_chat(..., history=)` takes history, and `Flow.run` accepts
  `prompt=None` plus `message_history=` / `deferred_tool_results=` for resumed runs.
- **`guardrails`:** a free regex check with a Luhn checksum refuses card and SSN numbers *before any
  model is called* (spans confirm no agent ran and zero requests were spent); a small guard agent
  refuses off-topic and instruction-extraction requests (the main agent provably never runs); an
  output validator rejects personal data even though the prompt never mentions it (live runs showed
  it firing: the model drafted an email, was sent back, and rewrote); `ContentFilterError` and
  `UsageLimitExceeded` become blocked answers, and any other exception still propagates.
- **`mcp_tools`:** first built with the MCP server inside `agent.py`, used in process
  (`MCP(local=server)`). That undersold MCP, whose point is the process boundary, and left its
  "swap in a URL" claim as untested documentation, so it was rebuilt as a real service (see
  "Services" below). Pydantic AI 2.54's MCP integration uses `fastmcp`, not the `mcp` SDK, and its
  client does not install the server half. Live: exact date arithmetic from the service's tools (a
  leap-year February: 20 days, not the naive 19).
- **First dependency-bearing example: the isolated-environment path is now proven for real.** That
  surfaced gaps no fake runner could: (1) the generic tests skip it in the default environment, so
  the gate's isolated stage now also runs the generic tests and the copy-into-a-project test
  (`GENERIC_TESTS`, narrowed with `-k`); (2) `fastmcp` raises a plain `ImportError`, not
  `ModuleNotFoundError`, when its server half is missing, so the skip logic (`import_example`, the
  conftest pre-import) catches `ImportError` for examples that declare dependencies, and the test
  files probe for the server half specifically; (3) `add_agent.py`'s `uv add` step had never been
  tested and now is.
- **Two chicken-and-egg bugs in the gate**, both found by recording a brand-new example: the offline
  suite required every example to have a transcript before the gate could record one, and the docs
  build failed on a link to a not-yet-recorded run. Transcript existence is now checked in its own
  stage *after* the live stage, and the docs generator drops the "See it run" line for an example
  with no recording yet.
- **Transcript quality:** a run that paused is rendered as "The run paused: waiting for a decision
  on approve issue_refund({...})", not a raw repr full of provider noise; the human-in-the-loop smoke
  input is the large refund so its recorded run shows the pause and the resume.
- **Verified:** the complete gate over all 14 examples (hermetic offline suite, each example's live
  tests and smoke run, mcp_tools in its own environment, 100% coverage of 768 statements, every
  transcript present and current) for under a cent of model spend.

## Services machinery (built with step 6, before Temporal needs it)

Decision: prove the `services` half of the machinery on something small first, so Temporal (step 7)
inherits a tested lifecycle instead of building and debugging one. `mcp_tools` is that example.

- **Declaration:** `services = ["mcp-server"]` plus a `[service.mcp-server]` table (container `port`,
  the `env` variable that receives the address, a `url` template with `{address}`), and
  `service/docker-compose.yml`. The manifest validates that each listed service has a table and
  vice versa, that the compose file exists, and the port/env/url shapes.
- **Lifecycle (`scripts/services.py`):** `docker compose -p <unique> up -d --build --wait` (the
  compose healthcheck is what `--wait` waits on), then `docker compose port <service> <port>` to
  learn the host port Docker chose (compose publishes `"127.0.0.1::8000"`: loopback only, free
  port), then `down -v --remove-orphans` in a `finally`, even if starting failed halfway. Everything
  goes through an injectable runner, so every branch is tested without a daemon. A real run left
  zero containers and zero networks behind.
- **Two honest outcomes besides pass/fail:** Docker unusable (daemon down, not installed, no
  Compose) is *unverified* with Docker's own reason, spending nothing and failing the check unless
  `--allow-unverified`; a service that won't start is *failed* with the container logs. Verified for
  real by pointing `DOCKER_HOST` at a socket that doesn't exist.
- **The environment carries the address:** every stage for that example (isolated offline tests,
  live tests, the smoke run) gets the variable, so the agent reads `McpDeps.server_url` from
  `MCP_SERVER_URL`. `record_example.py` run on its own treats an example with services as
  unverified unless that variable is already set.
- **Testing without Docker until the last layer:** the server's functions directly; the server run
  as a local subprocess on a free port for the offline tests; the real container only in the gate.
  `test_dependencies` (the server half of fastmcp) is layered on for tests but is not installed into
  a user's project, because using the agent needs nothing beyond the template.
- **Generic tests** that run an agent skip an example whose service variable is unset
  (`import_example(example, running=True)`), so the default suite never needs Docker.
- **`add_agent.py`** copies `service/` to `services/<name>/` (the server is a separate deployable,
  not part of `agent/`), prints how to start it, and generates a smoke test and eval starter that
  skip unless the service variable is set.
- **Coverage** includes `examples/*/service/server.py`: the server's code is example code too.
- **Bugs this found** (all in code that had no real service to exercise it): the transcript check
  excluded every example with services, leaving an empty selection (so the gate "passed" its own
  check by running no tests); `uv add` was never tested; and the isolation rule keyed only on
  `dependencies`, so an example needing only test packages or a service would have run without its
  generic tests.
- **For step 7:** Temporal reuses all of this. It needs a `service/docker-compose.yml` that
  publishes 7233 (the image `temporalio/temporal` is already on this machine), a `[service.temporal]`
  table with `env = "TEMPORAL_ADDRESS"`, and a healthcheck.

## Implementation notes (vector-backed retrieval in `rag`, as built)

- **Decision: replace, not combine.** The request was to replace `rag`'s keyword search or combine the
  two. Measured on 15 labeled questions with real Gemini embeddings in a real Chroma: keyword first for
  12 (MRR 0.80), vector first for 15 (MRR 1.00), and reciprocal-rank fusion with the vector side
  weighted 1x, 2x and 3x first for 14 (MRR 0.97). The hybrid was worse because one spurious keyword hit
  outranked the right vector answer whatever the weight, so the keyword half was removed. The old
  keyword search lives on in `test_live.py` as the baseline retrieval is measured against.
- **What it is.** `RagDeps` carries a Chroma address (`CHROMA_URL`, a Docker service with the image pinned
  to the client's version, 1.5.9: `latest` was a minor behind), an `Embedder`, and the collection. The
  embedding model follows the LLM's provider (Google, OpenAI) or `AGENT_EMBEDDING_MODEL`; under the
  offline test model it is Pydantic AI's `TestEmbeddingModel`; with Anthropic it must be set, and the
  error says so. `ensure_index` names the collection after the model and a hash of the passages and fills
  it only if it is not full, so editing a document or changing the model builds a new collection.
- **Nearest is not relevant.** A vector search always returns the nearest passages, so `MAX_DISTANCE`
  (0.37, cosine, the middle of the measured gap) drops the clearly unrelated: the right passage was never
  farther than 0.31 across all 15 test questions, unrelated ones 0.43 or more away (nearest 0.426). A live
  test checks the cutoff sits 0.03 clear of both, so a change of embedding model says when to re-measure.
  (The first cutoff, 0.40, was set from about ten questions' distances; measuring all 15 moved it.) For a question that is near the topic but not covered ("Do you sell
  tents?", 0.35) the cutoff cannot help, and the model correctly said it could not find the answer.
- **Dependency finding.** `chromadb-client` (the slim HTTP client) and `chromadb` (the full engine) both
  provide the `chromadb` module and overwrite each other; the full one then runs in "http-only" mode.
  So the agent depends on the client only and there is no in-process Chroma for tests. The offline tests
  use the real service with a scripted embedder (each text maps to a vector the test chose, so cosine
  distances are known exactly), skipped without `CHROMA_URL`.
- **Tested:** index contents, a full index not rebuilt, a partial one completed, one index per model,
  ranking and exact distances, the cutoff, the limit, the tool's output and ledger, the citation check, the
  agent loop; mutation checks (no cutoff, always re-embed, wrong metric, no per-run cache) were all caught.
  Live: retrieval measured against the baseline, the right passage never lost to the cutoff, unrelated
  questions return nothing, and the agent end to end (a paraphrase, a two-part question, a code-specific
  question that must not be answered from the neighbouring notice, and one not covered).
- **Breaking for `rag`:** `RagDeps` no longer works without the service and `search` / `tokens` are gone.
  Pre-release, no known users.

## Implementation notes (planner-executor, as built)

- **What it is.** Four moving parts: a planner agent whose output type is a `Plan` (steps with `id`,
  `instruction`, `depends_on`) and which never calls a tool; `check_plan`, plain code that rejects a
  plan (and, as the planner's output validator, sends it back); a scheduling loop that runs, in
  parallel, every step whose dependencies are done and gives each executor only its own step and the
  results it named; and a synthesizer that writes the answer from what completed. It differs from
  `supervisor` (the model decides each delegation as it goes) and from `pipeline` / `fan_out` (the
  shape is fixed in code): here the model chooses the shape once and code holds it to the rules.
- **Domain:** four invented cities (population, area, founded), so a model cannot know them and must
  use `get_city`; questions chosen so the answers are exact (a density of 1200.0; a 150.0% difference).
  A deps ledger (`deps.calls`) records every lookup that really ran.
- **Failure handling, tested:** a failed step is `failed`; every step that needs it, directly or through
  others, is `skipped` and never reaches an executor; unrelated steps finish; nothing completing raises
  `AllStepsFailedError`; `UsageLimitExceeded` and cancellation end the run rather than counting as a
  step failure. A mutation check (steps run one at a time, results leaked to every executor, skip
  cascade stopped early) was caught by the tests, after one gap was found and closed: a cascade that
  must finish with no round left to run.
- **The finding that shaped it.** The real model (Gemini 3.1 Flash-Lite) wrote its "compare them" step
  with an empty `depends_on` in 9 of 10 sampled plans, even after the rule and an example were put in
  the prompt. The step then ran in the same round as the lookups, and the answer was still right (the
  executors could look cities up and the synthesizer did the arithmetic), so a correct answer hid a
  wrong plan. The fix is in code: a plan must end in **one final step** that everything feeds into
  (`check_plan`), which turns that mistake into several "loose ends" the check names. Its limit is
  documented: a calculation step that declares nothing but is used by the final step passes (2 of 10
  sampled plans), harmlessly here.
- **The rejection message is part of the prompt.** Saying only what was wrong, the planner repeated the
  same plan three times and used its whole retry budget (recorded in an early transcript). Saying what to
  change, computed from the loose ends ("make 's4' the final step by setting its depends_on to include
  ['s1', 's2', 's3']"), fixed it on the first retry in 11 of 12 sampled plans. The output retry budget
  is 3 for headroom.
- **Live:** against Gemini: the densest city and its density (`Quillhaven`, `1200.0`), a calculation over
  two lookups (`150.0`), and a city that does not exist (the answer says so and no total is invented), plus
  the plan's shape (all three cities looked up, independent lookups in one round, a step that depends on
  others, planner first and synthesizer last). Of 21 runs of the live suite with the one-final-step rule in place, 20
  passed; the one failure could not be reproduced and its cause is unknown, because the gate then
  reported only log lines.
- **Generic change:** `release_check.py` now reports a failed stage with pytest's `FAILED` line and
  assertion detail (`failure_summary`) instead of the last five lines of output, which for a live test
  are usually captured HTTP logs. This was found because of the unreproducible failure above.

## Implementation notes (step 7b, Temporal, as built)

- **What it is.** `Agent(..., capabilities=[TemporalDurability(...)])`, a workflow class derived from
  `PydanticAIWorkflow` that lists the agent in `__pydantic_ai_agents__`, and `PydanticAIPlugin` on the
  client. (`TemporalAgent` is deprecated.) The extra is only `temporalio>=1.34,<2`, which is the
  example's `dependencies` pin. The server is `temporalio/temporal:1.8.0` (the CLI's own tag, which is
  the same image as `latest` today; pinned so the gate runs against one server), started with
  `server start-dev --headless` and healthy in under two seconds.
- **Domain:** an order desk with `check_stock` and a `shipping_quote` whose carrier API is down the first
  time it is asked about each shipment, so the retry is visible. `RETRY_POLICY` is 5 attempts with
  backoff; every activity has a 30 s timeout.
- **Offline tests need the server.** `WorkflowEnvironment.start_local()` downloads a binary, so a
  hermetic suite cannot use it (this corrects the plan's earlier guess). The tests skip without
  `TEMPORAL_ADDRESS` and the gate supplies it; coverage still reaches 100% through the gate. They run
  against the real server with `TestModel` as the model and assert on the **server's event history**.
- **What the tests prove:** a failing tool is retried and the model never sees it; the model-request
  activity runs once per request; the history of a retried tool shows only its final attempt (so the
  failures are kept in the carrier's own ledger); the retry policy is exhausted at 5 attempts and then
  fails the run, without asking the model again; a non-retryable `ApplicationError` is tried once; a run
  that cannot finish raises `RunTimedOut`; a worker shut down mid-tool-call is replaced and the model is
  asked exactly twice in total; and a worker run as a **separate process and `SIGKILL`ed** mid-call is
  replaced, which takes about the 30 s activity timeout because nothing is reported to the server.
- **Live:** against Gemini and the real server: the quote matches the independently computed 20.30, the
  carrier really failed first, the model saw no retry prompt, the server recorded attempt 2 for the
  carrier call and one start per model request, and the demo script runs.
- **Surprises worth keeping:**
  - The sandbox re-executes the workflow's module, so the template's modules (which read `.env`) must be
    imported inside `workflow.unsafe.imports_passed_through()`.
  - A workflow cannot live in `__main__`, and the agent's name (so its activity names) differed between
    the worker and the sandbox in script mode. The demo block re-imports the module under its real name.
  - A bug in workflow code does not fail the run: Temporal retries the workflow task forever and the
    caller hangs (a mistyped `r.usage()` did exactly this). Every run needs an `execution_timeout`.
  - Two workflows that list one agent register its activities twice and the worker refuses to start.
  - Pydantic AI's `invoke_agent` span does not appear for a run in a workflow (`LogfirePlugin` adds
    Temporal's own `StartWorkflow` / `RunActivity` spans), so the span-based "every agent ran" check cannot
    see it; the live test reads the agent's activity names from the server's history instead.
  - A copied agent (`add_agent.py temporal --name orders`) was run in a scratch copy of the repo: its
    generated smoke test passes against its own `services/orders` server and skips without one.
- **Generic changes:** `tests/test_services.py` now accepts a compose file that names a pinned published
  image where it used to demand a `Dockerfile`. `AGENTS.md` records the rules above.
- **Not done, on purpose:** the transcript of a run shows the model's view, in which the carrier never
  failed; the retry is shown by the tests and the README, not by `sample_run.md`.

## Implementation notes (step 7a, Monty, as built)

- **What it is.** Not `pydantic-monty` used directly: Pydantic AI's integration lives in a separate
  package, `pydantic-ai-harness`, whose `CodeMode` capability hides the agent's regular tools behind
  one `run_code` tool; the model writes Python that calls them as `await tool(arg=...)`, run in the
  Monty sandbox. The example is `code_mode`; its extra is `pydantic-ai-harness[code-mode]` (which
  pulls in `pydantic-monty`). The harness is pre-1.0 and its minor tracks Pydantic AI's, so the pin is
  `>=0.54,<1` and the two are bumped together.
- **Domain:** expense reports, invented and deterministic (23 expenses, five currencies, three
  employees): a question needs many tool calls and exact arithmetic, which is what code is for. A deps
  ledger (`deps.calls`) records every tool call that really ran on the host, so tests check what the
  model's code *did*, not what it said.
- **Measured:** with `Literal` categories in the tool types the model needed 2-3 requests for 14-72
  host tool calls and got the exact answers; without them it compared against `'Travel'`, failed, and
  needed 5-6. The prompt also warns about two Monty limits found by testing: `next()` over a generator
  expression fails (a generator expression evaluates to a list), and the code is type-checked against
  tool signatures before running (`x = None` then passed as `str` is rejected).
- **Sandbox tests are real:** hostile code runs in the real sandbox, and the assertions are about the
  host: a file not created, a secret not returned, exactly `MAX_TOOL_CALLS` calls reaching the host
  for a 1000-iteration loop, a `while True` stopped at `max_duration_secs`, a memory bomb refused,
  `socket` / `subprocess` unresolvable, `time.time()` unsupported. The sandbox has no `open` at all
  until `os` is imported, so the tests assert the invariant, not Monty's wording.
- **Live:** three questions with answers worked out independently (a total across currencies,
  `1520.12`; the employee with the most meal spend, `E3` at `296.78`; one conversion, `121.94`), plus
  a check that the host-side tool calls are at least 3x the model requests (the pattern's payoff).
- **Transcripts** render a `run_code` call as the code the model wrote, not a clipped argument.
- **First example with a runtime `dependencies` entry**, so `add_agent.py`'s `uv add` is now exercised
  by a real example, not a synthetic one.

## Implementation notes (step 5, as built)

- **Generated, not written.** `docs/gen_pages.py` (run by `mkdocs-gen-files`) builds every page
  from the repo's own files: the README split by its `##` sections (a missing section raises
  `SectionNotFound` naming what exists), `AGENTS.md` as "Design notes", `CHANGELOG.md`, and for
  each example its README, `sample_run.md` (nested under "Recorded run") and its source in
  Material content tabs (`agent.py`, each prompt, `example.toml`, `test_example.py`,
  `test_live.py`). Relative links are rewritten to site pages where one exists and to GitHub
  otherwise; code fences are never touched.
- **The nav is set by the generator** (`mkdocs_gen_files.config["nav"]`), from the examples that
  exist, so a new example needs no edit to `mkdocs.yml`. A `SUMMARY.md` + `literate-nav` approach
  was tried first and dropped: the nav file is added after `exclude_docs` runs, so it was published
  as a stray page. Examples are listed in `DISPLAY_ORDER` (`scripts/example_manifest.py`); an
  unlisted one is appended alphabetically.
- **`examples/README.md`** is a generated index (`scripts/examples_index.py`), so the examples
  are browsable on GitHub too; a test fails if it is stale.
- **Pages workflow** (`.github/workflows/docs.yml`): builds with `uv run --only-group docs mkdocs
  build --strict` (verified in an isolated docs-only environment) and deploys with the official
  Pages actions on pushes to `main` that touch the docs sources. It needs Settings → Pages →
  Source: "GitHub Actions", set once by hand. Unlike the release gate it spends nothing and needs
  no secrets, so it is a workflow.
- **`tests/test_docs.py`**: the generator's pure functions, that every page is in the nav and
  every internal link resolves, that `mkdocs.yml`'s URLs match the scripts', that the examples
  index is current, and a real `mkdocs build --strict` when MkDocs is installed.
- **MkDocs is pinned `<2`.** Material's own build banner warns that MkDocs 2.0 will break
  plugins and themes; `properdocs`, a continuation of 1.x that Material already installs, is the
  drop-in if 1.x is ever abandoned.
- **`--prune`** now also removes the docs, `examples/README.md`, `scripts/examples_index.py`,
  `tests/test_docs.py` and the `docs` dependency group from `pyproject.toml` (and relocks) —
  the part of step 1's prune that had been deferred.
- **Verified:** strict build clean in the full and the docs-only environments, every page serves,
  and the pages were looked at in a browser (home, getting started, agents, design notes, and
  pattern pages with their recorded runs and source tabs). Looking found a bug the build could
  not: GitHub renders a list straight after a `**bold**` line, but MkDocs runs its items into one
  paragraph, and the example READMEs and transcripts are written GitHub-style. The generator now
  puts a blank line before every such list (fence-aware, idempotent, tested on every generated
  page). Not checked: dark mode, narrow/mobile layout.

## Implementation notes (step 4, as built)

- **`scripts/live_run.py`:** the shared, offline-testable core. `run_live` times one real call to
  an example's `run`; `verify` lists what is wrong in plain English (not a `RunResult`, no steps,
  a step not labeled for the example, an `expected_tools` entry never called, cost over budget);
  `render_transcript` builds `sample_run.md` purely from the `RunResult`. Per-step tokens and
  cost come from each `ModelResponse` (steps share one cumulative `RunUsage`, so it cannot be
  split per step); cost is `None` when Pydantic AI has no price for the model (Ollama, `test`).
- **`scripts/record_example.py`:** the per-example worker (`<name>...|--all`, `--no-write`,
  `--json`). All examples in one invocation share one event loop. A failed check never
  overwrites the last good transcript.
- **`scripts/release_check.py`:** the orchestrator. Offline suite first (stop if it fails), then
  each example in its own `uv run [--with <dep>...] python scripts/record_example.py` process,
  with `AGENT_COST_LIMIT` set to its `cost_budget_usd` (skipped for `ollama:` models, whose cost
  can't be computed). An example with extra dependencies runs its own offline tests in that
  isolated environment first, and a failure there skips the live (paid) call. A summary gives
  pass/fail/unverified counts, tokens and spend, and the exit code gates on it.
- **Manifest:** optional `expected_tools` (set for `supervisor` and `tool_calling`) and
  `cost_budget_usd` (default 0.25).
- **`services`:** examples that declare them are reported *unverified* and fail the check unless
  `--allow-unverified`. Starting and stopping the services themselves is deferred to step 7,
  where Temporal is the first example that needs it.
- **No CI.** The gate is a manual, local step by design (it spends money and needs a key); an
  earlier draft added a `release-check` workflow, which was removed. `.github/workflows/ci.yml`
  still runs only the offline suite. Transcripts are recorded locally with `--record` and
  committed.
- **Prune:** `add_agent.py --prune` removes the release tooling and its tests.
- **Tested offline** (`tests/test_live_tools.py`): transcripts and verification from real
  examples run under `TestModel`, plus the orchestration with fake subprocess runners. The live
  path was also exercised for free against a local Ollama model: the offline suite, then three
  examples in isolated processes, with correct pass/fail reporting.
- **Scope grew once real models were involved.** The requirement became: every agent in every
  example runs to completion against a real model and is verified, with no untested example
  code. Running the gate against Gemini 3.1 Flash-Lite found real defects that no offline test
  could (`TestModel` ignores tool results and instructions):
  - `tool_calling`'s tool echoed its query, so the model searched until it hit the request
    limit. It now looks up Python release notes in an injected table, with all three error
    outcomes (`ModelRetry` for a malformed version, `ToolFailed` for an unknown one).
  - `supervisor`'s only worker had the instructions `[TASK TYPE A]`. It now coordinates a real
    analyst and writer, and the smoke input explicitly asks for research then writing (with a
    vaguer input the model legitimately skipped the analyst).
  - `evaluator_optimizer`'s critic rejected even ordinary adjectives, so the loop burned the
    whole cap. Its criteria now target factual claims; it converges in two or three rounds and
    still refuses an item whose own name makes an unverifiable claim.
- **Live tests per example** (`examples/<name>/test_live.py`, marked `eval`): inputs with an
  unambiguous expected result, semantic assertions, a requirement that every `Agent` the module
  defines ran (read from spans by `evals/trace.py:traced_run`, since a supervisor's workers run
  inside a tool call and are in no step), and a run of the module's `__main__` demo (via
  `runpy` with `alter_sys=True`, so Pydantic can resolve forward references as under
  `python -m`). Where the real model varies (how many rounds the critic takes) the tests assert
  the loop's invariants for whichever path occurs.
- **Coverage gate:** `coverage` (dev dependency) measures `examples/*/agent.py` over the offline
  and live tests together; `fail_under = 100`. It caught an untested branch in `fan_out`
  (cancellation must propagate, not count as a failed worker), now covered.
- **Release check order:** offline suite (under coverage) → per example in isolation: offline
  tests if it has dependencies, live tests, smoke run + transcript → coverage gate → summary.
  A failure stops that example before the next paid stage.
- **Model-agnostic by design.** The gate must work however `.env` is configured:
  - *Offline suite:* a root `conftest.py` forces `AGENT_MODEL=test` at import time unless the
    command line selects the live tests, so it no longer depends on `.env`'s model or key (it
    used to crash on import when `.env` named a provider whose key was absent). It reads `-m`
    from `sys.argv`/`PYTEST_ADDOPTS` because `tests/conftest.py` imports `agent.config` before
    any pytest hook runs.
  - *Live assertions:* checked against a second, very different model (a local 30B Ollama
    model), which exposed assertions that encoded Gemini's behavior: exact request counts (a
    model may need an output retry), `phone is None` (a model wrote the string `"None"`), a list
    of "unavailable" phrases, and a requirement that the supervisor not research a simple
    request. They now assert properties that hold for any capable model.
  - *What remains is a capability floor:* the model must call tools and return valid structured
    output. A model that can't fails with Pydantic validation errors, which is a verdict on the
    model, not the example.
  - Transcripts record their model in the header; `--record` overwrites them.
- **Still to do for this step:** commit the recorded `sample_run.md` files, link them from the
  example READMEs, and add a test that every example has one.

## Implementation notes (step 3, as built)

- **`agent/runs.py`:** `Step`, `RunResult` and `Flow`, with tests in `tests/test_runs.py`.
  `RunResult.usage` is a stored field, because steps sharing a `RunUsage` all return the same
  object and summing would double-count. `Flow.run` passes the shared usage and limits to every
  step and records it on completion (so parallel steps appear in completion order); a step that
  raises records nothing.
- **All nine examples** return `RunResult[...]` from their `run_*` helper; the four flows use
  `Flow` in place of hand-passed `usage=` / `usage_limits=`. Their own tests also assert on
  `.steps` and `.usage`.
- **Manifest:** `[smoke.<agent_variable>]` tables (`call_tools`, `output`) replace `smoke_tools`,
  `smoke_output` and `[entrypoint] agent`; `[entrypoint]` is now just `deps` and `run`.
- **Generic tests:** the smoke test drives `run` with the manifest's per-agent overrides and
  asserts on the `RunResult` (steps labeled for the example, usage within `USAGE_LIMITS`,
  opted-in tools called). The content-filter and cost-enforcement tests check every agent in
  the module directly. `tests/agent_finder.py` is the shared "find the agents a module holds"
  helper (used by the safety net too).
- **`add_agent.py`:** the generated smoke test calls the copied agent's `run` and applies only
  the configured agents' overrides; the eval starter reads `result.output`;
  `evals/helpers.py:run_fixture_dataset` takes a run helper that returns a `RunResult`.
- **Docs:** README, AGENTS.md and the changelog describe the contract, with an Upgrade note.

## Implementation notes (step 2, as built)

- **Trace labels:** `agent_label(__name__)` in `agent/logging.py`, used by every example;
  tested in place (`tests/test_examples.py`) and in a copied agent
  (`tests/test_add_agent.py`).
- **New examples:** `extraction`, `router`, `pipeline`, `fan_out`, `evaluator_optimizer`,
  each with README, manifest and a `test_example.py` using `FunctionModel` to test the
  orchestration. `sample_run.md` files are deferred to step 4 (they need `record_example.py`
  and a live key).
- **`smoke_output`:** new optional manifest table. `TestModel`'s generated junk fails a real
  output validator, so `extraction` supplies the output smoke tests should return; the
  generic tests (`tests/examples_support.py:smoke_model`) and the generated smoke test use it.
- **Safety net:** also scans dicts/lists/tuples at module level; examples keep every Agent
  reachable from module scope (router's specialists are variables as well as dict values).
- **`examples/conftest.py`** sets dummy provider keys so `pytest examples/<name>` works alone.
- **Manifest `agent`:** the generic tests drive it directly; for orchestrated examples it is
  the first agent (classifier, outline step, worker, generator), and the orchestration is
  tested by the example's own tests. **Superseded by step 3**, which removed this key; the
  generic tests now run the whole flow through `run`.

## Implementation notes (step 1, as built)

- **Manifest loader:** `scripts/example_manifest.py` (standard library only), shared
  by `add_agent.py` and the tests; `pythonpath = ["scripts"]` in pytest config. It
  stays after `--prune`.
- **Schema as built:** `title`, `pattern`, `summary`, `smoke_input`, `[entrypoint]`
  required; `smoke_tools`, `dependencies`, `env`, `services`, `templated` optional.
  `expected_tools` and `cost_budget_usd` are deferred to the live tier (step 4).
- **Prompts:** `PROMPTS_DIRS` in `agent/prompts/templates.py`; `examples/__init__.py`
  registers each example's `prompts/` so examples run in place. On copy, prompt
  files are renamed `<example>*.txt` → `<name>*.txt` and matching `load_prompt(...)`
  calls are rewritten.
- **Renaming:** only `blank` (`templated = true`) has its symbols renamed; other
  examples keep theirs, which is safe because each agent is its own module.
- **Generated files:** `tests/test_agents_<name>.py`, `evals/test_<name>.py`,
  `evals/fixtures/<name>.json`; the script runs `ruff check --select I --fix` and
  `ruff format` on them, and `tests/test_add_agent.py` verifies they pass lint.
- **Safety net:** `tests/conftest.py` pre-imports every module under `agent.agents`
  and `examples`, skipping examples whose third-party dependencies are absent.
- **`--prune` keeps `blank`** so the script remains useful, which is also why
  `tests/test_safety_net.py` uses `examples/blank`.
- **Known gap, fixed in step 2:** each example hard-codes its Agent `name=`
  (`"supervisor"`, `"tool_agent"`, `"worker_a"`), so a copy called `triage` still
  appears as `supervisor` in Logfire. See "Trace labels".
- **Not yet done:** the `docs` dependency group (so prune does not yet edit
  `pyproject.toml`), the live tier, `sample_run.md` files, MkDocs, the new examples.
