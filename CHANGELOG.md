# Changelog

All notable changes to this template are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Entries are written for people who
have cloned the template: what changed, and whether you need to do anything.

## [Unreleased]

## [0.3.0] - 2026-10-07

Version 0.3.0 turns the template from "one agent plus three stubs" into a library of seventeen working
patterns that you add to your own project with one command, each run against a real model, with a
documentation site.

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
- **Python 3.13 is still the minimum**, and 3.14 is now supported. Python 3.15 is not yet.
- **Some examples read their own environment variables** (an embedding model, the address of a service). They are
  optional, and only matter if you add that example; see "Configuration" in the README and `.env.example`.

### Added
- **Seventeen example patterns in `examples/`**, each with its source, prompt, README, offline and live tests, and a
  recorded run against a real model:
  - *Basics:* `blank`, `single`, `conversation` (message history, a bounded window, streaming).
  - *Tools and data:* `tool_calling`, `extraction` (an output validator and a retry budget), `rag` (documents embedded
    and searched by meaning in Chroma, with citations checked against what was retrieved), `mcp_tools` (the tools of
    an MCP server running as a Docker service) and `code_mode` (the model writes Python that calls your tools, in a
    sandbox).
  - *Several agents:* `supervisor`, `planner_executor` (a plan written as data, checked and run by code), `router`,
    `pipeline`, `fan_out` and `evaluator_optimizer`.
  - *Safety and reliability:* `human_in_the_loop` (pause a risky action for approval), `guardrails` (checks on input and
    output, failures turned into safe answers) and `temporal` (a durable workflow: failing tools are retried, a dead
    worker is replaced).
- **`scripts/add_agent.py`**, the one way to add an agent: an interactive menu, or `add_agent.py <example> --name <name>`.
  It copies the example and its prompt, scaffolds a smoke test and an eval starter, installs the example's extra
  packages, copies its service (if it has one) to `services/<name>/`, and tells you which environment variables to set.
  `--prune` removes the examples you did not use, and the docs and release tooling with them.
- **`RunResult` and `Flow`** (`agent/runs.py`): every `run_*` helper returns the output, the total usage and one step per
  agent run, whatever the pattern, so a call site does not change when an agent grows from one step to several.
- **A documentation site** at https://tmtabor.io/agent-template/, generated from the README, the examples and the other
  documents, so nothing is written twice. Each pattern has a page with an explanation, when to use it and when not to,
  its source, and its recorded run. Two guides: "Which pattern should I use?" and an FAQ.
- **`CONTRIBUTING.md`, `MAINTAINING.md` and `SECURITY.md`** (private vulnerability reporting is on), a logo, and a coverage
  badge in the README. `--prune` removes them, since they are about the template and not your project.
- **Python 3.14** support: `pyproject.toml` lists it, CI runs lint and the offline suite on 3.13 and 3.14, and
  `tests/test_python_versions.py` keeps the README badge, the classifiers and the CI matrix in agreement.
- **A release check** (`scripts/release_check.py`) for maintainers: the offline suite, then each example against a real
  model in its own environment (its live tests, a smoke run, its Docker service started and stopped for it), a gate that
  every line of every example's code ran, and the recorded runs. It is manual and local, and is not part of CI.
- **Examples can need more than the template.** `example.toml` declares extra `dependencies` (installed only when you add
  that example), `test_dependencies`, `services` (a `docker-compose.yml` the release check starts), smoke-test
  overrides, `expected_tools` and a `cost_budget_usd`.
- **Smaller additions:** `agent_label(__name__)` labels each agent's traces with its own name (`triage`, `triage.worker`);
  `evals/trace.py` reports every agent and tool call a run made, from its spans; `evals/helpers.py` holds the shared
  evaluators and runner; `Flow.run` can resume a run with no new prompt (`message_history=`, `deferred_tool_results=`);
  `load_prompt` searches `PROMPTS_DIRS` so examples run in place.

### Changed
- **A new README and documentation home.** They open with a logo, the line "Pick a pattern, edit the prompt, ship it.",
  badges and a pitch, then a three-step "Get started", the use cases, the four opinions baked in, and next steps. The
  maintainer sections moved to `MAINTAINING.md`.
- **`tool_calling` and `supervisor` now do real work.** Their placeholder tool and worker were replaced (a real model
  looped on the old echoing tool until it hit the request limit): `tool_calling` looks up Python release notes with a
  tool that shows all three error outcomes, and `supervisor` coordinates a real analyst and writer.
- **The three pattern stubs moved from `agent/agents/` to `examples/`** and are copied into your project on demand.
- **The unit-test safety net** also covers `examples/` and agents held in module-level dicts, lists and tuples, and
  `tests/test_safety_net.py` no longer depends on a chosen agent.
- The GitHub Actions in `.github/workflows/` are on their current major versions (Node 24).

### Fixed
- **The offline test suite is hermetic.** A root `conftest.py` forces `AGENT_MODEL=test` unless the command line selects the
  live tests (`-m eval`), so `uv run pytest` passes with no provider key whatever `.env` configures. Before, it crashed on
  import if `.env` named a provider whose key was missing.

### Removed
- `scripts/choose_pattern.py`, the canonical re-export in `agent/agents/__init__.py`, and `tests/test_stubs.py` (replaced by
  `tests/test_examples.py`).

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

[Unreleased]: https://github.com/tmtabor/agent-template/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/tmtabor/agent-template/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/tmtabor/agent-template/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/tmtabor/agent-template/releases/tag/v0.1.0
