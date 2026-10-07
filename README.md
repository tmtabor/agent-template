<div align="center">
  <a href="https://tmtabor.io/agent-template/">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
      <img src="docs/assets/logo-light.svg" alt="agent template" height="64">
    </picture>
  </a>
</div>
<div align="center">
  <h3>Pick a pattern, edit the prompt, ship it.</h3>
</div>
<div align="center">
  <a href="https://github.com/tmtabor/agent-template/actions/workflows/ci.yml"><img src="https://github.com/tmtabor/agent-template/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/tmtabor/agent-template/actions/workflows/docs.yml"><img src="https://github.com/tmtabor/agent-template/actions/workflows/docs.yml/badge.svg?branch=main" alt="Docs"></a>
  <a href="MAINTAINING.md#the-release-check"><img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Ftmtabor%2Fagent-template%2Fmain%2Fbadges%2Fcoverage.json" alt="Coverage"></a>
  <img src="https://img.shields.io/badge/python-3.13%20%7C%203.14-blue.svg" alt="Python 3.13 and 3.14">
  <img src="https://img.shields.io/badge/Pydantic%20AI-v2-e92063.svg" alt="Pydantic AI v2">
  <a href="https://github.com/tmtabor/agent-template/blob/main/LICENSE"><img src="https://img.shields.io/github/license/tmtabor/agent-template.svg" alt="License"></a>
</div>
<p align="center">
  <a href="https://tmtabor.io/agent-template/">Documentation</a> ·
  <a href="examples/">Examples</a> ·
  <a href="docs/pages/choosing-a-pattern.md">Which pattern should I use?</a> ·
  <a href="docs/pages/faq.md">FAQ</a>
</p>

---

**Agent Template** is a clean, opinionated starting point for building AI agents using [Pydantic AI](https://pydantic.dev/docs/ai/), with ready-to-go scaffolding for seventeen popular agent patterns: tool calling, retrieval, multi-agent workflows, human approval, durable execution and more. Run one script, pick a pattern, and you get the agent, its prompt, an offline test and an eval starter in your own project, as code you own. There is no framework to depend on.

Every pattern has been run against a real model: each comes with a recorded run you can read, live tests that check what the agent actually did and tests that cover every line of its code. The guardrails are on from the start (limits on requests, tokens and spend) and any model is one setting away.

## Get started

```bash
# 1. Create your project: click "Use this template" on GitHub, or clone it
git clone https://github.com/tmtabor/agent-template.git my-agent && cd my-agent
uv sync --group dev
cp .env.example .env        # then add the API key for your model provider

# 2. Add an agent: pick a pattern from the menu
uv run python scripts/add_agent.py

# 3. Edit its prompt (agent/prompts/<name>.txt), then run the tests
uv run pytest
```

That gives you `agent/agents/<name>.py`, its prompt, a smoke test and an eval starter. Run `add_agent.py` again for each further agent; each can use a different pattern. The [setup and commands](README.md#setup-and-commands) below cover the rest, and [Which pattern should I use?](docs/pages/choosing-a-pattern.md) helps you choose.

## What are you building?

From a first agent to a long-running multi-agent system, each of these is a pattern you add with one command. Each has working code, tests, and a recorded run against a real model.

### Your first agent

One agent, one prompt, one typed output. Start from `blank` (empty) or `single` (a worked example).

```bash
uv run python scripts/add_agent.py single --name summarizer
```

```python
from agent.agents.summarizer import run_agent

result = await run_agent("Hello, what can you do?")
result.output  # the validated output
result.usage  # tokens and requests for the whole run
```

**Build this →** [single](examples/single/) · [blank](examples/blank/)

### An agent that uses your tools

Give the model tools that call your systems, with errors it can recover from, or use the tools of an existing MCP server.

```bash
uv run python scripts/add_agent.py tool_calling --name releases
```

```python
from agent.agents.releases import run_tool_agent

result = await run_tool_agent("What changed in Python 3.13 compared with 3.12?")
```

**Build this →** [tool_calling](examples/tool_calling/) · [mcp_tools](examples/mcp_tools/)

### Answers from your own documents

Documents are embedded and stored in a vector database (Chroma, running as a Docker service), so questions are matched by meaning and every cited source is checked against what was really retrieved.

```bash
uv run python scripts/add_agent.py rag --name support_docs
docker compose -f services/support_docs/docker-compose.yml up -d --wait   # the database
```

```python
from agent.agents.support_docs import run_rag

result = await run_rag("How long can I send my hiking footwear back for my money?")
result.output.sources  # ['returns-policy']
```

**Build this →** [rag](examples/rag/)

### Structured data from text

Turn free text into a validated schema, with an output validator that sends a wrong answer back for correction.

```bash
uv run python scripts/add_agent.py extraction --name contacts
```

```python
from agent.agents.contacts import run_extraction

result = await run_extraction(
    "Hi, it's Ada Lovelace from Analytical Engines Ltd. Reach me at ada@example.com."
)
result.output  # a validated Contact
```

**Build this →** [extraction](examples/extraction/)

### Several agents working together

Six shapes, from the most predictable to the most flexible: a fixed `pipeline`, a `router` that picks a specialist, a parallel `fan_out`, an `evaluator_optimizer` loop, a `planner_executor` whose plan code checks, and a `supervisor` that decides as it goes. [Which one?](docs/pages/choosing-a-pattern.md)

```bash
uv run python scripts/add_agent.py router --name support
```

```python
from agent.agents.support import run_router

result = await run_router("I was charged twice for my subscription this month.")
result.steps  # each agent run, in order
```

**Build this →** [pipeline](examples/pipeline/) · [router](examples/router/) · [fan_out](examples/fan_out/) · [evaluator_optimizer](examples/evaluator_optimizer/) · [planner_executor](examples/planner_executor/) · [supervisor](examples/supervisor/)

### Actions a person must approve

Pause a risky tool call until someone approves it, reject impossible requests before anyone is asked, or check input and output with guardrails.

```bash
uv run python scripts/add_agent.py human_in_the_loop --name refunds
```

```python
from agent.agents.refunds import run_refunds

result = await run_refunds("Order A100 arrived with a broken sole. Please refund the full $84.50.")
```

**Build this →** [human_in_the_loop](examples/human_in_the_loop/) · [guardrails](examples/guardrails/)

### Work that must not be lost

Run the agent as a Temporal workflow: a failing tool is retried, and a crashed worker is replaced, without repeating the model calls that already finished. Temporal runs as a Docker service.

```bash
uv run python scripts/add_agent.py temporal --name orders
docker compose -f services/orders/docker-compose.yml up -d --wait   # the Temporal server
```

```python
from agent.agents.orders import run_order_desk

result = await run_order_desk(
    "I'd like to order 3 gizmos for Norway. Are they in stock, and what is the shipping?"
)
```

**Build this →** [temporal](examples/temporal/)

### Exact answers over many lookups

Let the model write code that calls your tools in a loop and does the arithmetic, in a sandbox with hard limits, so one or two model requests do the work of dozens.

```bash
uv run python scripts/add_agent.py code_mode --name expenses
```

```python
from agent.agents.expenses import run_expenses

result = await run_expenses("What is the total of Maya's travel expenses, in US dollars?")
result.output.amount_usd
```

**Build this →** [code_mode](examples/code_mode/)

### A conversation

Remember earlier turns, keep the context window bounded, and stream replies as they are generated.

```bash
uv run python scripts/add_agent.py conversation --name chat
```

```python
from agent.agents.chat import run_chat

first = await run_chat("Hi! My name is Priya and I'm planning a trip to Lisbon.")
second = await run_chat("What's my name?", history=first.all_messages())
```

**Build this →** [conversation](examples/conversation/)

See [all seventeen patterns](examples/README.md), each with its source and a recorded run.

## Why this template

It is opinionated on purpose. Four opinions are baked in, so you can tell whether they are yours:

- **Copy, don't depend.** `add_agent.py` copies a pattern into your project. There is no library to import and nothing to upgrade in place; the code is yours to change.
- **Guardrails from the start.** Every agent has limits on requests and tokens, an optional spend cap, and a response the provider blocks raises an error instead of coming back half finished. A misconfigured provider fails at import, not at the first request.
- **Observable by default.** Runs are traced with no per-agent setup: to the console until you give it a Logfire token.
- **Any model, one config.** `AGENT_MODEL` is the one setting. The patterns' live tests assert behavior that holds for any capable model, not one model's wording.

## Stack

- Python 3.13 and 3.14, uv
- Pydantic AI v2 (agents, tools) + pydantic-evals (evals)
- Logfire (observability)
- pytest + pytest-asyncio

## Setup and commands

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

### Variables only some examples read

An example reads these only if you add it; `add_agent.py` names the ones to set, and the release check sets the service addresses itself.

| Variable | Example | Default | Notes |
|---|---|---|---|
| `AGENT_EMBEDDING_MODEL` | `rag` | follows the provider of `AGENT_MODEL` (Google or OpenAI) | The embedding model for retrieval. Anthropic has no embedding model, so with an Anthropic `AGENT_MODEL` set this, for example to `google:gemini-embedding-001`; the key for that provider must be set too. |
| `CHROMA_URL` | `rag` | `http://127.0.0.1:8000` | Where the Chroma server is. The Docker service publishes on a random free port, so set this to the address `add_agent.py` shows how to find. |
| `MCP_SERVER_URL` | `mcp_tools` | `http://127.0.0.1:8000/mcp` | The MCP server's URL. Set it to the published port, as for `CHROMA_URL`. |
| `TEMPORAL_ADDRESS` | `temporal` | `127.0.0.1:7233` | The `host:port` of the Temporal server. Set it to the published port, as for `CHROMA_URL`. |

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
| `planner_executor` | A planner writes the whole plan as data; code checks it and runs it, independent steps in parallel; a last agent answers |
| `tool_calling` | An agent whose tools call external systems |
| `extraction` | Free text to a validated schema, with an output validator and retry budget |
| `rag` | Answer from your own documents by meaning, with embeddings in a Chroma vector database (a Docker service; needs `chromadb-client`), and cite only what was really retrieved |
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
  `pydantic-ai-harness[code-mode]`, `temporal` needs `temporalio`, `rag` needs `chromadb-client`), and tells you about any environment variables it needs.

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

## Next steps

- **Make it yours.** Edit the prompt, replace the output schema, and add your tools: [Customizing the prompt](README.md#customizing-the-prompt) and [Adding tools](README.md#adding-tools). Each pattern's README ends with how to adapt it.
- **Test it for real.** Grow the eval fixtures for your task, and run `uv run pytest -m eval` with your key: [Evals](README.md#evals).
- **Set your limits.** Tune `USAGE_LIMITS` and set `AGENT_COST_LIMIT` before real use: [Usage limits](README.md#usage-limits).
- **See what it did.** Add a Logfire token and every model call and tool call is traced: [Observability](README.md#observability).
- **Replace the stand-ins.** The examples use invented data and demo services; swap in your own. The [FAQ](docs/pages/faq.md) says what to check before production.
- **Join in.** Report a problem or send a fix: [Contributing](CONTRIBUTING.md).

## Projects using agent-template

- **[job-agent](https://github.com/tmtabor/job-agent)**: a daily job-scanning agent. It fetches postings from several sources, filters and scores them against a candidate profile with an LLM, and emails a ranked digest. Runs on GitHub Actions.
- **[content-agent](https://github.com/tmtabor/content-agent)**: a multi-brand agent that generates social posts, blogs and newsletters, built with Pydantic AI, FastAPI/HTMX and a local Ollama model.
- **[oss-notifier-agent](https://github.com/tmtabor/oss-notifier-agent)**: an LLM-triaged good-first-issue digest for GitHub repos, delivered by email. Runs on GitHub Actions, no server required.

Built something with it? Open a pull request to add it here.

## Contributing and maintaining

- [CONTRIBUTING.md](CONTRIBUTING.md): how to set up, what to run before a pull request, and how to add or change an example.
- [MAINTAINING.md](MAINTAINING.md): the release check, cutting a release, and the documentation site.
- [SECURITY.md](SECURITY.md): how to report a vulnerability, privately.

## License

BSD 3-Clause — see [LICENSE](LICENSE).
