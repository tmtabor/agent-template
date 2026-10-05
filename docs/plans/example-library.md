# Example agent library — plan

Status: steps 1-6 implemented, including the services machinery (step 5 awaits the one-time Pages
setting); step 7 pending. Date: 2026-10-05.

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
| RAG / retrieval | Retrieval tool over local docs, with citations | none (in-memory) at first |
| Human-in-the-loop | Deferred tools requiring approval before risky actions | none |
| Conversational with memory | Message history across turns, plus streaming | none |
| Guardrails | Input/output validation, content-filter handling, cost limits | none |
| MCP tools | Consuming an MCP server's tools | MCP extra |

Heavier examples, built in step 7 (they need extra dependencies or services and
exercise the isolated-environment and `services` machinery):

| Pattern | Shows | Extra dependencies / services |
|---|---|---|
| Code execution (Monty) | The model writes Python that runs in a sandboxed interpreter, with only the tools and inputs the example exposes | `pydantic-monty` (confirm the package name and its Pydantic AI integration when building) |
| Durable workflow (Temporal) | An agent run as a durable, resumable Temporal workflow: retries, crash recovery, long waits | Temporal SDK / Pydantic AI's Temporal integration; a Temporal server (`services = ["temporal"]`, started from the example's `docker-compose.yml`) |

Still deferred beyond step 7: planner-executor and vector-DB-backed retrieval.

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
- `run_*` does **not** take `message_history=` yet. The web-UI skill keeps calling `agent.run()`
  directly; revisit when the conversational-memory example is built (step 6), where the design
  of multi-turn flows will say what a history parameter should mean for multi-step runs.
- The supervisor's workers stay **inside** the supervisor's single step (usage is total either
  way), which keeps the example teaching the standard `usage=ctx.usage` delegation pattern.
- Temporal (step 7) may need a serializable form of the result, since runs happen in a worker
  process. Plan: add a `to_record()` view later; the contract above should not need to change.

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
7. **Monty and Temporal examples.** `mcp_tools` already proved the `dependencies` machinery (step 6);
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
- Monty and Temporal are the least certain examples: their package names, versions
  and Pydantic AI integration points must be checked against current docs when step 7
  starts, and the plan may change then.
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
