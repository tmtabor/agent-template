# Changelog

All notable changes to this template are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Entries are written for people who
have cloned the template: what changed, and whether you need to do anything.

## [Unreleased]

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
