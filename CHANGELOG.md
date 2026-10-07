# Changelog

All notable changes to this template are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Entries are written for people who
have cloned the template: what changed, and whether you need to do anything.

## [Unreleased]

### Upgrade notes
- **The template no longer ships an agent.** `agent/agents/` is empty and there is no
  canonical `run_agent` / `AgentOutput` / `AgentDeps` / `agent` re-export. Run
  `uv run python scripts/add_agent.py` (once per agent) and import each agent from its own
  module, e.g. `from agent.agents.triage import ...`. Code importing the canonical names from
  `agent.agents` must change.
- **`scripts/choose_pattern.py` is gone.** `add_agent.py` replaces it and the old
  `add_agent.py <name>` scaffold: `add_agent.py supervisor --name triage`, or
  `add_agent.py blank --name newsletter` for what the old script produced. Existing clones are
  unaffected until you pull this change; if you already chose a pattern, your agent keeps
  working but `agent/agents/__init__.py` no longer needs the canonical import.
- **`evals/test_pass_fail.py`, `evals/test_llm_judge.py` and `evals/fixtures/example.json` are
  removed.** Each agent now gets `evals/test_<name>.py` and `evals/fixtures/<name>.json` from
  `add_agent.py`; the shared evaluators moved to `evals/helpers.py`. Copy your fixtures to the
  new file name.
- **`agent/prompts/system.txt` is gone.** Each agent has `agent/prompts/<name>.txt`.
- **`run_*` helpers return a `RunResult`, not the bare output.** Read `.output` for what you
  used to get back: `result = await run_agent(...)`, then `result.output`. `result.usage` is the
  total usage and `result.steps` records each agent run (`result.steps[0].result` is the native
  Pydantic AI result). Applies to `run_agent`, `run_tool_agent`, `run_supervisor` and every new
  example's helper; agents you copy with `add_agent.py` get the same shape.
- **The `agent-web-ui` skill's `chat.py` imports one agent module** you point it at (see the
  skill's "Before you start"), instead of the canonical names.

### Added
- The environment variables the examples read (`AGENT_EMBEDDING_MODEL`, `CHROMA_URL`, `MCP_SERVER_URL`,
  `TEMPORAL_ADDRESS`) are documented in `.env.example` and in a new table in the README's Configuration section,
  and a test fails if an example declares one that is not.
- Python 3.14 is supported: `pyproject.toml` lists it in the classifiers, CI runs the offline suite on 3.13 and
  3.14, and the README badge says so. The full release check passed on 3.14.6, and
  `tests/test_python_versions.py` keeps those claims in agreement. The floor stays 3.13.
- `SECURITY.md`: how to report a vulnerability (privately, through GitHub's advisory form), what is in scope,
  and what is not. `--prune` removes it, since it is about the template and not your project.
- A coverage badge in the README, fed by `badges/coverage.json`, which `scripts/release_check.py` writes after
  a complete clean run (never after a partial one); the badge reads `coverage: 100%`. `--prune` removes it.
- `CONTRIBUTING.md` and `MAINTAINING.md`: how to contribute, and how to run the release check, cut a
  release and maintain the docs site, moved out of the README. Both are pages on the site.
- Two guides, the only hand-written pages on the site: "Which pattern should I use?" and an FAQ.
- A logo (light and dark variants), a favicon and a site header mark, in `docs/assets/`.
- `examples/`: a library of example agents (`blank`, `single`, `supervisor`,
  `tool_calling`), each with source, prompt, README and an `example.toml` manifest.
- `scripts/add_agent.py` is now the one way to add an agent: an interactive menu of patterns
  (or `add_agent.py <example> --name <name>`) that copies the example, its prompt, and
  scaffolds a smoke test and an eval starter. `--prune` removes the examples you don't need.
- Tests parametrized over every example (`tests/test_examples.py`, content-filter and
  cost-limit tests); the smoke test drives each example's whole flow and checks the result, and `tests/test_add_agent.py`, which runs the real script into a scratch
  copy of the repo and checks that what it generates imports, passes its own smoke test and
  lint, and has collectable evals.
- Five more examples: `extraction` (output validator + retry budget), `router` (classifier
  plus code dispatch), `pipeline` (chained steps with gates), `fan_out` (parallel workers,
  tolerating a failed one) and `evaluator_optimizer` (generate/critique loop with a round
  cap). Each has its own `test_example.py` covering its orchestration.
- `agent_label(__name__)` in `agent/logging.py`: Agent run spans are labeled with the name you
  gave the agent (`triage`, `triage.worker`), not the example's. The examples use it.
- Five more examples, each verified against a real model: `rag` (retrieval over documents, with
  citations an output validator checks were really retrieved), `human_in_the_loop` (a tool that
  pauses for approval, `args_validator` rejecting impossible requests before anyone is asked, an
  approver you plug in, and a ledger checked against what the model claims), `conversation`
  (message history, a turn-based window, streaming), `guardrails` (a PII check in code, an LLM
  topic guard, an output validator, provider filters and budget limits turned into safe answers)
  and `mcp_tools` (the tools of an MCP server that runs as its own Docker service, reached over
  HTTP, with the address in deps and a clear error when the server is down).
- **Services.** An example can declare a service it needs running: `services = [...]` plus a
  `[service.<name>]` table in `example.toml` (the container port, the environment variable that
  receives its address, and a URL template), and `service/docker-compose.yml`. The release check
  (`scripts/services.py`) builds and starts it with `docker compose up --build --wait`, finds the
  port Docker chose, passes the address to the example's tests, and always tears it down. If Docker
  isn't available the example is reported *unverified* with the reason (and fails the check unless
  `--allow-unverified`), never passed. `test_dependencies` names packages only an example's tests
  need, which `add_agent.py` does not install into your project. `add_agent.py` copies an example's
  `service/` to `services/<name>/`, and its generated tests skip unless the service is running.
- `rag` now retrieves by meaning: passages are embedded (Pydantic AI's `Embedder`) and stored in
  Chroma, which runs as a Docker service, instead of being matched on keywords in memory. Measured
  against the keyword baseline with real embeddings, the right passage was first for 15 of 15 questions
  against 12 of 15, and a keyword/vector hybrid was worse than vectors alone (14 of 15), so the keyword
  search was removed rather than combined. **Breaking for `rag`:** `RagDeps` has a Chroma address and an
  embedder instead of being self-contained, `search` and `tokens` are gone, and it needs the Chroma
  service and `chromadb-client`. An index is named after the embedding model and the documents, so a
  change of either builds a new one.
- `planner_executor`, an example of plan-then-execute: a planner writes the whole plan as data
  (steps with `depends_on`), code checks it (`check_plan`: unique ids, real dependencies, no cycles,
  one final step) and sends a bad plan back with what to change, runs it a round at a time with the
  independent steps in parallel, gives each executor only the results it depends on, and skips only the
  steps that needed a failed one. Found with a real model: it rarely declares a step's dependencies, so
  the one-final-step rule lives in code, and the rejection says what to change, not only what is wrong.
- `scripts/release_check.py` now reports the pytest failure (the `FAILED` line and the assertion) when
  a live stage fails, instead of the last log lines.
- `temporal`, an example of a durable agent: `TemporalDurability` turns the agent's model requests and
  tool calls into Temporal activities and its loop into a workflow, so a failing tool is retried
  without asking the model again, and a worker killed mid-run is replaced by another that finishes it.
  The Temporal server is a Docker service (`service/`, image pinned). Its tests run against the real
  server and read its event history: they kill a worker (tidily, and with `SIGKILL` of a separate
  process), exhaust the retry policy, refuse a non-retryable failure a retry, and check that a run
  that cannot finish raises `RunTimedOut` instead of hanging.
- `code_mode`, an example of Pydantic AI's code mode (`pydantic-ai-harness`'s `CodeMode`, running the
  model's Python in the Monty sandbox): the model writes code that calls the agent's tools in loops,
  so a question that needs dozens of tool calls and exact arithmetic takes two or three model
  requests. Its tests run real hostile code (files, environment, clock, network, subprocess,
  infinite loops, memory, runaway tool loops) in the real sandbox and check that the host is untouched.
  The first example with a runtime dependency: `add_agent.py` installs
  `pydantic-ai-harness[code-mode]`. Transcripts now show code the model wrote as code.
- `run_*` helpers may resume a run with no new prompt: `Flow.run` accepts `prompt=None` with
  `message_history=` and `deferred_tool_results=`.
- The release gate runs a dependency-bearing example's generic tests (and its copy-into-a-project
  test) in its own environment, and checks transcripts after the live stage rather than before it.
- A documentation site (MkDocs Material, published to GitHub Pages by a `Docs` workflow),
  generated entirely from the README, `AGENTS.md`, `CHANGELOG.md` and the examples by
  `docs/gen_pages.py`: nothing is written twice, and every pattern gets a page with its README,
  recorded run and source. Preview it with `uv run --group docs mkdocs serve`. `examples/README.md`
  is a generated, browsable index of the examples (`scripts/examples_index.py`). Enable it once in
  Settings → Pages → Source: "GitHub Actions". A new `docs` dependency group holds the tooling.
- `scripts/release_check.py`, the live pre-release gate: the offline suite under coverage, then
  each example in its own `uv run` environment under a spend cap — its real-model live tests
  (`examples/<name>/test_live.py`, which also require that every agent the example defines ran),
  and a smoke run — and a gate that every line of every example's source was exercised.
  `scripts/record_example.py` writes each example's `sample_run.md` transcript from its
  `RunResult`. The gate is a manual, local step and is not part of CI. `example.toml` gains optional
  `expected_tools` and `cost_budget_usd`. `evals/trace.py` (`traced_run`) reports every agent and
  tool call a run made, from its spans. `add_agent.py --prune` removes the release tooling.
- Two examples now do real work. `tool_calling` looks up Python release notes with a tool that
  shows all three error outcomes (its old placeholder tool echoed the query, so a real model
  looped on it), and `supervisor` coordinates a real analyst and writer instead of one
  placeholder worker. The `evaluator_optimizer` critic's criteria were tightened so the loop
  converges in two or three rounds.
- `agent/runs.py`: `RunResult` (output, total usage, per-step results) and `Flow`, which runs
  agents against one shared budget and records each step. Every example's `run_*` returns a
  `RunResult`, so tests, evals and callers can see how an answer was produced.
- Per-agent `[smoke.<agent>]` tables in `example.toml` (`call_tools`, `output`), for agents whose
  smoke tests need a tool called or whose validators reject `TestModel`'s generated junk.
- The offline test suite is now hermetic: a root `conftest.py` forces `AGENT_MODEL=test` unless
  the command line selects the live tests (`-m eval`), so `uv run pytest` passes with no provider
  key whatever `.env` configures. Previously it crashed on import if `.env` named a provider whose
  key was missing.
- `evals/helpers.py`: shared eval evaluators, fixture loader and dataset runner.
- `load_prompt` searches `PROMPTS_DIRS`, so examples can run in place.

### Changed
- The GitHub Actions in `.github/workflows/` are on their current major versions (`checkout` v7, `setup-uv` v10,
  and v5 or v6 of the Pages actions), which run on Node 24; the old ones printed a Node 20 deprecation warning.
- Each example's README now opens with a fuller explanation of the pattern, a "Use it when" list, and a "Look
  elsewhere when" list that points to the pattern that fits better. "See it run" moved to after "What it shows".
- On the docs site, a pattern page now puts the source first and the recorded run last, as a collapsed block whose
  title gives the model, step count and cost; the "See it run" link opens it.
- **A new README and docs home page.** Both now open with the logo, the line "Pick a pattern, edit the
  prompt, ship it.", badges and a pitch, then a three-step "Get started", the use cases under "What are
  you building?" (tabs on the site), "Why this template" (the opinions baked in), next steps, and the
  projects built on the template. The reference sections follow, unchanged apart from "Quickstart"
  becoming "Setup and commands". The README's "Releasing the template" and "Documentation site" sections
  are gone (see `MAINTAINING.md`). The site is now at https://tmtabor.io/agent-template/
  (`tmtabor.github.io/agent-template` redirects to it).
- `add_agent.py --prune` also removes `CONTRIBUTING.md` and `MAINTAINING.md`, which are about the
  template and not your project.
- The three pattern stubs moved from `agent/agents/` to `examples/` and are copied into your
  project on demand; the unit-test safety net now also covers `examples/`.
- The unit-test safety net also finds agents held in module-level dicts, lists and tuples.
- `tests/test_safety_net.py` and the `TestModel` recipe (`examples/single/test_example.py`)
  no longer depend on a chosen agent.

### Fixed
- The template's own tests (`tests/test_add_agent.py`) failed with 33 errors as soon as you had added an agent, which is the
  first thing "Get started" asks you to do. They now build their scratch projects without your agents, prompts and
  evals. That the template itself ships no agents is checked in CI, in this repository only.
- The release check ran coverage through the `coverage` console script, whose launcher in a fresh environment cannot
  see the packages `uv run --with` adds, so on a fresh clone `code_mode`, `rag` and `temporal` skipped their tests
  and failed the gate. It now runs `python -m coverage`.

### Removed
- `scripts/choose_pattern.py`, the canonical re-export in `agent/agents/__init__.py`, and
  `tests/test_stubs.py` (replaced by `tests/test_examples.py`).

## [0.2.0] - 2026-10-04

### Upgrade notes
- **`CLAUDE.md` is now `AGENTS.md`.** If you customized it, move your edits over. Tools that
  look for `CLAUDE.md` need an `@AGENTS.md` import or a copy.
- **Evals:** `pydantic_evals.Dataset(...)` now requires `name=`. Add it to any dataset you
  wrote; `evals/test_pass_fail.py` already does.
- **Unit tests no longer call agent tools by default.** If you wrote tests that relied on
  tools being called automatically, opt in with `TestModel(call_tools=["name"])`
  (recipe in `tests/test_safety_net.py`).
- **If you copied the pytest config,** add `asyncio_default_test_loop_scope = "session"` and
  `asyncio_default_fixture_loop_scope = "session"`; without them evals fail after the first.
- **Callers of `run_*` should handle `ContentFilterError`** (see Added). It propagates
  instead of being retried or returned half-finished.
- **Default models changed** to Sonnet 5.5 (agent) and Opus 5.5 (judge). Pin
  `AGENT_MODEL` / `AGENT_JUDGE_MODEL` if you want the old ones.

### Added
- Optional `AGENT_COST_LIMIT` (USD, e.g. `0.50`), off by default. When set it is passed as
  `cost_limit` in every stub's and scaffolded agent's `USAGE_LIMITS`. It is only enforceable
  for models with known pricing; leave it unset for others (e.g. `ollama:`), whose cost is
  unknown. With no limit set, Pydantic AI emits no cost warning.
- `ToolFailed` in the tool error convention: raise it for expected, terminal failures the
  model can work around (not found, unsupported). Unlike `ModelRetry` it spends no retry
  budget. `agent/tools/example.py` demonstrates it.
- `RaiseContentFilterError` on every agent: a content-filtered response now raises
  `ContentFilterError` out of `run_*`. The web-UI skill's chat router handles it.
- Span-based agentic evals: every dataset case gets `MaxModelRequests` / `MaxToolCalls`
  budgets, and fixtures accept optional `expected_tools`, `expected_trajectory` and
  `expected_arguments` keys (`ToolCorrectness`, `TrajectoryMatch`, `ArgumentCorrectness`).
- Logfire settings: `AGENT_SERVICE_NAME` (default `agent`; rename per project),
  `AGENT_ENVIRONMENT` (falls back to `LOGFIRE_ENVIRONMENT`) and `AGENT_LOG_CONTENT`
  (default `true`; `false` keeps prompts, outputs and tool arguments out of traces).
  Evals force content on because `ArgumentCorrectness` needs tool arguments.
- `CHANGELOG.md`, and a convention in `AGENTS.md` for keeping it current.

### Changed
- Upgraded to Pydantic AI 2.54.0 (from 2.3.0), `pydantic-evals` 2.54.0, Logfire 5.1.1,
  `pydantic-settings` 2.15.0, `python-dotenv` 1.2.4, pytest 9.1.1, pytest-asyncio 1.4.0
  and ruff 0.16.10. Minimum versions in `pyproject.toml` were raised to match.
- Default models: `anthropic:claude-sonnet-5-5` for the agent and
  `anthropic:claude-opus-5-5` for the judge.
- `agent/tools/example.py` search now goes through a replaceable `_search_backend()`.
- ruff 0.16 formats Python code blocks in Markdown; the README was reformatted accordingly.
- Unit tests no longer call agent tools by default. The `tests/conftest.py` safety net now
  uses `TestModel(call_tools=[])`; a default `TestModel()` called every tool with junk
  arguments, which failed any tool that validates input with `ModelRetry` and really ran
  tools with side effects. Tests that want a tool executed opt in with
  `TestModel(call_tools=["name"])` (see `SMOKE_TOOLS` in `tests/test_stubs.py` and the recipe
  in `tests/test_safety_net.py`). If you wrote tests that relied on tools being called
  automatically, add the opt-in.

### Fixed
- `test_fixture_dataset` crashed under `pydantic-evals` 2.54 because `Dataset` requires a
  `name` (see Upgrade notes).
- Evals made with a real model failed with `RuntimeError: Event loop is closed` on every
  test after the first. Agents are module-level, so the provider's HTTP client was bound to
  the first test's event loop, which pytest-asyncio then closed. `pyproject.toml` now pins
  `asyncio_default_test_loop_scope` and `asyncio_default_fixture_loop_scope` to `session`;
  if you copied the old pytest config, add both settings. Found while running the evals
  against a local Ollama model.

## [0.1.0] - 2026-08-06

Initial release: an opinionated starting point for a production-quality Pydantic AI agent.

### Added
- Three agent patterns (`single`, `supervisor`, `tool_calling`) behind a canonical import in
  `agent/agents/__init__.py`, switched with `scripts/choose_pattern.py`, plus
  `scripts/add_agent.py` for additional independent agents.
- Import-time `Settings` validation that works for any pydantic-ai provider, with `.env`
  loading so keys set only in `.env` reach the provider SDKs.
- `USAGE_LIMITS` guardrail (request and token limits) on every run.
- Logfire observability with automatic console fallback.
- Unit tests that run on `TestModel` with no credentials; evals (pass/fail dataset and
  LLM-as-judge) with separate agent and judge models.
- Skills for scaffolding a web UI (`agent-web-ui`) and a double-clickable macOS launcher
  (`macos-launcher`), plus CI (ruff and unit tests) and a BSD-3-Clause license.

[Unreleased]: https://github.com/tmtabor/agent-template/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/tmtabor/agent-template/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/tmtabor/agent-template/releases/tag/v0.1.0
