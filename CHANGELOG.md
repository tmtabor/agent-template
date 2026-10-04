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
- **Callers of `run_*` should handle `ContentFilterError`** (see Added). It propagates
  instead of being retried or returned half-finished.
- **Default models changed** to Sonnet 5.5 (agent) and Opus 5.5 (judge). Pin
  `AGENT_MODEL` / `AGENT_JUDGE_MODEL` if you want the old ones.

### Added
- `cost_limit` (USD, default `0.50`) in every stub's and scaffolded agent's `USAGE_LIMITS`.
  It is only enforced for models with known pricing; for others (e.g. `ollama:`) a
  `CostNotFoundWarning` is emitted and the request and token limits remain the guardrail.
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

### Fixed
- `test_fixture_dataset` crashed under `pydantic-evals` 2.54 because `Dataset` requires a
  `name` (see Upgrade notes).

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
