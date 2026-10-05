# Example agent library — plan

Status: steps 1 and 2 implemented (step 2 not yet committed); steps 3-7 pending. Date: 2026-10-05.

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
expected_tools = ["delegate_to_worker_a"]   # tools that must be called in smoke runs
cost_budget_usd = 0.10            # live smoke run must stay under this
dependencies = []                 # PEP 508 requirements beyond the template's own
env = []                          # extra environment variables required
services = []                    # e.g. ["temporal"]; needs docker-compose.yml

[entrypoint]                      # where tests and the release check find the agent
agent = "supervisor_agent"
deps = "SharedDeps"
run = "run_supervisor"
```

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
   `cost_budget_usd`. It also refreshes each `sample_run.md`. Run it from a `workflow_dispatch` or tag-triggered CI
   job with the API secret, or locally.
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
the same small dataclass, defined once in `agent/runs.py`:

```python
@dataclass
class Step:
    agent: str                  # the agent's label (see "Trace labels")
    result: AgentRunResult      # the native Pydantic AI result, untouched

@dataclass
class RunResult(Generic[OutputT]):
    output: OutputT             # the run's own output; for flows, built in code from the steps
    steps: list[Step]           # every agent run, in order (a list: labels repeat)
    def usage(self) -> RunUsage          # total across steps (they share one RunUsage)
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

**Manifest.** Smoke configuration becomes per agent, keyed by the agent's variable name, and
replaces `smoke_tools`, `smoke_output` and `[entrypoint] agent` (which only ever meant "the
agent the tests happen to drive"). `[entrypoint]` keeps `deps` and `run`.

```toml
[smoke.supervisor_agent]
call_tools = ["delegate_to_worker_a"]

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

**Open items to settle while building it.**
- Whether `run_*` should accept `message_history=`, so the web-UI skill can use the helper
  instead of bypassing it.
- Whether the supervisor's workers should appear as their own steps (the delegation tool
  would record them through deps) or stay inside the supervisor's single step; usage is
  total either way.
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
   `sample_run.md` from a `RunResult`), the isolated per-example runs and the release CI
   job. Commit the `sample_run.md` files here.
5. **Docs site.** MkDocs Material config, gen-files generation, Pages workflow,
   README links.
6. **Remaining roadmap examples:** RAG/retrieval, human-in-the-loop, conversational
   with memory, guardrails and MCP tools — the ones that need no services.
7. **Monty and Temporal examples.** The first examples with real extra dependencies:
   - **Monty (code execution):** `dependencies` in `example.toml`; tests skip in the
     root environment and run in the example's isolated one. Decide how the sandbox's
     limits (time, memory, allowed calls) are shown and tested, and that it never runs
     under the offline `TestModel` tier with real code execution unless that is safe.
   - **Temporal (durable workflow):** the first example with `services`. Needs a
     `docker-compose.yml`, release-check logic to start and stop the server, a clear
     "unverified (no Docker)" result when it can't, and a README on running a worker
     alongside the agent. Offline tests use Temporal's in-process test environment if
     it exists, otherwise they are limited to import and wiring checks.
   This step is also what proves the `dependencies`/`services` machinery from
   step 4 on real cases; expect small fixes to the manifest schema and release check.

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
  tested by the example's own tests. **Superseded by step 3**, which has the generic tests
  run the whole flow through `run` and removes this key.

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
