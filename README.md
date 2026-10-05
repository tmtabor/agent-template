# Agent Template

Opinionated general-purpose AI agent template. Clone and start building.

**[Read the documentation](https://tmtabor.github.io/agent-template/)** · **[Browse the example patterns](examples/)** — each with its source, tests and a recorded run against a real model.

## Stack
- Python 3.13, uv
- Pydantic AI v2 (agents, tools) + pydantic-evals (evals)
- Logfire (observability)
- pytest + pytest-asyncio

## Quickstart

```bash
# Install dependencies
uv sync --group dev

# After uv sync, install Claude Code skills for pydantic-ai and logfire
uvx library-skills install --all --claude

# Copy and configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Add an agent: pick a pattern from the menu (or name one, e.g.
# `add_agent.py supervisor --name triage`); see "Agents" below
uv run python scripts/add_agent.py

# Run unit tests (no API calls, no API key needed)
uv run pytest

# Run evals — requires a real API key, see Evals below
uv run pytest -m eval

# Lint
uv run ruff check .

# Format
uv run ruff format .
```

## Project structure

```
agent/
├── config.py          # Settings — validates the AGENT_MODEL provider at import time (raises if misconfigured)
├── logging.py          # Logfire setup — configure_logging(), get_logger()
├── agents/             # YOUR agents, one module each — empty until you run add_agent.py
├── tools/example.py    # Canonical tool pattern — copy and adapt
└── prompts/
    ├── <name>.txt       # One prompt per agent, written by add_agent.py
    └── templates.py      # load_prompt() loader

examples/               # The pattern library: blank, single, supervisor, tool_calling, … (see its README)
└── <pattern>/           #   agent.py, prompts/, example.toml, README.md, sample_run.md, tests
scripts/add_agent.py     # Add an agent from an example pattern — see "Agents" below
tests/    # Unit tests against TestModel — no API calls, no API key needed
evals/    # Per-agent eval starters + shared helpers — real API calls, run with -m eval
docs/ + mkdocs.yml          # The documentation site, generated from this README and examples/
.github/workflows/ci.yml    # CI: ruff check, format check, unit tests (no secrets needed)
.github/workflows/docs.yml  # Builds the docs site and publishes it to GitHub Pages
```

## Configuration

All settings are read from the environment (see `.env.example`). Agent-specific
variables carry an `AGENT_` prefix so a generic name like `MODEL` in your shell
can't silently change the provider; API keys and `LOGFIRE_TOKEN` keep their
standard names because the provider SDKs read those exact variables directly.

| Variable | Default | Notes |
|---|---|---|
| Provider key (e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_BASE_URL`, …) | — | Whichever variable the provider behind `AGENT_MODEL` reads. Not declared on `Settings` — `Settings` validates it by asking pydantic-ai to build that provider at import time, so any provider pydantic-ai supports (including ones added in later pydantic-ai releases) is checked automatically, and it raises immediately if misconfigured — not a lazy/runtime check. |
| `AGENT_MODEL` | `anthropic:claude-sonnet-5-5` | The agent under test. Any pydantic-ai model string works, e.g. `google:gemini-2.0-flash` or `ollama:*` for local models (no API key needed, but `OLLAMA_BASE_URL` must be set). |
| `AGENT_JUDGE_MODEL` | `anthropic:claude-opus-5-5` | Used only by the LLM-as-judge evals. Kept separate from `AGENT_MODEL` to avoid self-assessment bias — keep it at least as capable as the agent model, not cheaper. |
| `LOGFIRE_TOKEN` | unset | If set, traces go to Logfire cloud. If unset, traces print to the console — no separate dev-mode flag needed. |
| `AGENT_COST_LIMIT` | unset | Optional per-run spend cap in USD (e.g. `0.50`). Off by default. Only set it for models with known pricing — for others (e.g. `ollama:`) the cost is unknown, so the cap can't be enforced and Pydantic AI warns. |
| `AGENT_SERVICE_NAME` | `agent` | Service name on Logfire traces. Rename it for your project. |
| `AGENT_ENVIRONMENT` | unset | Environment tag (`development`, `production`, …) on traces. Unset falls back to `LOGFIRE_ENVIRONMENT`. |
| `AGENT_LOG_CONTENT` | `true` | Whether traces include prompts, model outputs and tool arguments. Set `false` in production if they may be sensitive. Evals force it on, since `ArgumentCorrectness` reads tool arguments from spans. |
| `AGENT_LOG_LEVEL` | `INFO` | Standard Python logging level. |

## Agents

The template starts with **no agents**. When you want one, run `add_agent.py`
and pick a pattern from the menu; run it again for each further agent, each
with whatever pattern suits it.

```bash
uv run python scripts/add_agent.py                       # interactive menu
uv run python scripts/add_agent.py supervisor --name triage
uv run python scripts/add_agent.py blank --name newsletter
```

The patterns live in [`examples/`](examples/) — each is a folder with the agent's source,
its prompt, a README and an `example.toml`:

| Example | Pattern |
|---|---|
| `blank` | An empty agent: one output type, one prompt, no tools |
| `single` | One agent handles the whole task |
| `supervisor` | A supervisor delegates to specialized workers |
| `tool_calling` | An agent whose tools call external systems |
| `extraction` | Free text to a validated schema, with an output validator and retry budget |
| `rag` | Answer from your own documents with a search tool, and cite only what was really retrieved |
| `mcp_tools` | Use the tools of an MCP server that runs as its own Docker service |
| `code_mode` | The model writes Python that calls your tools in a sandbox (Monty): exact answers from one or two requests (needs `pydantic-ai-harness`) |
| `temporal` | A durable agent run as a Temporal workflow: failing tools are retried and a crashed worker is replaced, without repeating model calls (Temporal runs as a Docker service; needs `temporalio`) |
| `conversation` | Memory across turns, a bounded context window, and streaming |
| `human_in_the_loop` | Pause a risky tool call for approval, reject impossible ones first, resume the run |
| `guardrails` | Check input in code and with a guard model, validate output, turn failures into safe answers |
| `router` | A classifier picks a category; code dispatches to a specialist |
| `pipeline` | Fixed sequential steps, each output feeding the next, with gates |
| `fan_out` | Parallel workers via `asyncio.gather`, then an aggregator |
| `evaluator_optimizer` | A generator and a critic loop until the output passes or a cap is hit |

For each agent, `add_agent.py`:

- copies the example's module to `agent/agents/<name>.py` and its prompt to
  `agent/prompts/<name>.txt` (only `blank` renames its symbols; the others keep
  theirs, which is safe because each agent lives in its own module),
- scaffolds a smoke test, `tests/test_agents_<name>.py` (runs under `TestModel`, no API key),
- scaffolds an eval starter, `evals/test_<name>.py`, with a fixture file at
  `evals/fixtures/<name>.json`,
- copies the example's service, if it has one, to `services/<name>/` (`mcp_tools` ships its MCP
  server, a Dockerfile and a compose file; `temporal` a compose file for the Temporal server) and
  tells you how to start it,
- runs `uv add` for any extra dependencies the example declares (`code_mode` needs
  `pydantic-ai-harness[code-mode]`, `temporal` needs `temporalio`), and tells you about any environment variables it needs.

There is no shared "primary" agent. Import each agent directly from its own module. Every
`run_*` helper returns the same thing, a `RunResult` (`agent/runs.py`):

```python
from agent.agents.triage import run_supervisor

result = await run_supervisor("Summarize the benefits of unit tests")
result.output  # the validated output
result.usage  # total usage, across every agent run in the flow
result.steps  # each agent run, in order: Step(agent="triage", result=<AgentRunResult>)
```

A single agent is a one-step run, a router or pipeline a several-step run, so moving an agent
from one shape to the other never changes a call site. `result.steps[0].result` is the native
Pydantic AI result if you want its messages or run id.

Once you've picked what you need, `uv run python scripts/add_agent.py --prune` removes the
other examples (keeping `blank`), the docs and their tests. Nothing under `agent/` or `evals/`
depends on `examples/`.

## Usage limits

Each agent defines a `USAGE_LIMITS` constant passed to every run — a guardrail
against runaway agentic loops. `request_limit` caps model round-trips (each
tool-call iteration is one request); `total_tokens_limit` caps overall tokens. An optional spend cap in USD comes from `AGENT_COST_LIMIT` (off by default).
Exceeding any of them raises `UsageLimitExceeded` instead of silently burning
tokens. Tune the values in your agent module to fit your task; the supervisor
shares its budget with its workers so the limit bounds the whole delegation
tree.

Every agent also carries the `RaiseContentFilterError` capability, so a
response the provider filters (safety block or refusal) raises
`ContentFilterError` instead of being retried or returned half-finished. Like
`UsageLimitExceeded`, it propagates out of `run_*` for the caller to handle:

```python
from pydantic_ai.exceptions import ContentFilterError

try:
    result = await run_supervisor(user_input)  # whichever run_* your agent has
except ContentFilterError as e:
    ...  # e.message has the reason; e.body has the filtered response
```

## Adding tools

Copy `agent/tools/example.py`, implement your tool, register with `@<your_agent>.tool`. Use `ModelRetry` only for errors the LLM can fix by changing its input (bad query, out-of-range param), and `ToolFailed` for expected failures it can't fix but can work around (not found, unsupported) — log and re-raise everything else.

Unit tests don't run your tools by default: the `TestModel` safety net in `tests/conftest.py` calls none (a default `TestModel` calls every tool with junk arguments, which breaks tools that validate input and really runs ones with side effects). Test tool logic by calling the function directly, as `tests/test_tools.py` does, and opt in to an end-to-end call (recipe in `tests/test_safety_net.py`) with `TestModel(call_tools=["your_tool"])`.

## Customizing the prompt

Each agent's prompt is `agent/prompts/<name>.txt`, loaded via `load_prompt("<name>")` in
`agent/prompts/templates.py`; add more `.txt` files in the same directory and load them the
same way.

## Observability

All agent runs, tool calls, and model requests are automatically traced via
`logfire.instrument_pydantic_ai()` — no per-agent setup needed. Cloud vs.
console output is controlled by `LOGFIRE_TOKEN`, see Configuration above.

## Evals

Each agent gets its own eval starter, `evals/test_<name>.py`, from `add_agent.py`:

- A smoke eval, and a **dataset eval** driven by `evals/fixtures/<name>.json` (a
  `pydantic_evals` `Dataset`). Add cases to that JSON file to grow the eval; no code changes
  needed unless a case requires a new kind of check (then add an `Evaluator` alongside
  `ContainsExpected` in `evals/helpers.py`). Every case is also checked against behavioral
  budgets (`MaxModelRequests`, `MaxToolCalls`) read from the run's OpenTelemetry spans, so it
  grades how the agent got its answer, not just the answer. Tool-using agents can add optional
  keys to a fixture: `expected_tools` (`["a", "b"]`, any order), `expected_trajectory`
  (ordered tool names, scored by F1) and `expected_arguments`
  (`{"tool": "a", "args": {"q": "x"}}`).
- An **LLM-as-judge eval**, graded by `AGENT_JUDGE_MODEL` (see Configuration above); edit its criteria.

The shared evaluators and runner live in `evals/helpers.py`; the judge in `evals/judge.py`.

All of these share the same `@pytest.mark.eval` marker — there's no separate marker for the LLM-judge subset. `uv run pytest -m eval` runs all of them and requires a real API key; the LLM-judge evals also cost money (they make an extra model call per test to grade the output).

## Releasing the template (maintainers)

Before tagging a release, run the release gate yourself, locally. It is manual on purpose — it
makes real model calls and costs money — so it is not part of CI, which runs only the offline
tests.

```bash
# The provider key for AGENT_MODEL must be in .env or the environment
uv run python scripts/release_check.py            # check every example
uv run python scripts/release_check.py router     # or just some
uv run python scripts/release_check.py --record   # also refresh each example's sample_run.md
```

It runs the offline suite, then each example against the real model (its live tests and a smoke
run, each capped by the example's `cost_budget_usd`), and fails unless every example passes and
every line of every example's source was exercised. It prints a summary with tokens and spend.
It checks whichever model `AGENT_MODEL` names, so reconfigure `.env` as you like (the model needs
to handle tool calls and structured output; a model that can't will fail the gate). It takes a few
minutes and costs well under a dollar on a small model. See "Releasing" in
`AGENTS.md` for the details; `add_agent.py --prune` removes this tooling from your own project.

## Documentation site (maintainers)

The documentation site is generated from this README, `AGENTS.md`, `CHANGELOG.md` and the
`examples/` folders by `docs/gen_pages.py`. There are no hand-written pages to keep in sync, so to
change the docs, change those files; a new example appears in the site, and its navigation,
automatically.

```bash
uv run --group docs mkdocs serve           # preview at http://127.0.0.1:8000
uv run --group docs mkdocs build --strict  # what the workflow runs; fails on any broken link
uv run python scripts/examples_index.py    # regenerate examples/README.md after editing a manifest
```

The `Docs` workflow publishes the site to GitHub Pages on every push to `main` that touches the
docs sources. One-time setup: in the repository's Settings → Pages, set "Source" to "GitHub
Actions". `add_agent.py --prune` removes all of this from your own project.

## License

BSD 3-Clause — see [LICENSE](LICENSE).
