# Agent Template

Opinionated general-purpose AI agent template. Clone and start building.

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

# Pick an agent pattern (single / supervisor / tool_calling) — deletes the
# other stubs and rewires imports; see "Agent patterns" below
uv run python scripts/choose_pattern.py single

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
├── config.py         # Settings — validates the AGENT_MODEL provider at import time (raises if misconfigured)
├── logging.py         # Logfire setup — configure_logging(), get_logger()
├── agents/            # Three interchangeable stubs — pick one with scripts/choose_pattern.py
│   ├── __init__.py     #   canonical names (run_agent, AgentOutput, …) re-exported from the chosen stub
│   ├── single.py       #   one agent, one task (the default)
│   ├── supervisor.py    #   supervisor delegates to specialized workers
│   └── tool_calling.py  #   agent with tools that call external systems
├── tools/example.py   # Canonical tool pattern — copy and adapt
└── prompts/
    ├── system.txt       # Default system prompt — edit this first
    └── templates.py      # load_prompt() loader

scripts/choose_pattern.py   # Pick an agent pattern — deletes the other stubs, rewires imports
scripts/add_agent.py        # Scaffold an additional, independent agent — see "Multiple agents" below
tests/    # Unit tests against TestModel — no API calls, no API key needed
evals/    # Pass/fail + dataset + LLM-as-judge evals — real API calls, run with -m eval
.github/workflows/ci.yml    # CI: ruff check, format check, unit tests (no secrets needed)
```

## Configuration

All settings are read from the environment (see `.env.example`). Agent-specific
variables carry an `AGENT_` prefix so a generic name like `MODEL` in your shell
can't silently change the provider; API keys and `LOGFIRE_TOKEN` keep their
standard names because the provider SDKs read those exact variables directly.

| Variable | Default | Notes |
|---|---|---|
| Provider key (e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_BASE_URL`, …) | — | Whichever variable the provider behind `AGENT_MODEL` reads. Not declared on `Settings` — `Settings` validates it by asking pydantic-ai to build that provider at import time, so any provider pydantic-ai supports (including ones added in later pydantic-ai releases) is checked automatically, and it raises immediately if misconfigured — not a lazy/runtime check. |
| `AGENT_MODEL` | `anthropic:claude-sonnet-5` | The agent under test. Any pydantic-ai model string works, e.g. `google:gemini-2.0-flash` or `ollama:*` for local models (no API key needed, but `OLLAMA_BASE_URL` must be set). |
| `AGENT_JUDGE_MODEL` | `anthropic:claude-opus-4-8` | Used only by the LLM-as-judge evals. Kept separate from `AGENT_MODEL` to avoid self-assessment bias — keep it at least as capable as the agent model, not cheaper. |
| `LOGFIRE_TOKEN` | unset | If set, traces go to Logfire cloud. If unset, traces print to the console — no separate dev-mode flag needed. |
| `AGENT_LOG_LEVEL` | `INFO` | Standard Python logging level. |

## Agent patterns

Three stubs are provided — pick one:

- `agent/agents/single.py` — one agent, one task
- `agent/agents/supervisor.py` — supervisor delegates to specialized workers
- `agent/agents/tool_calling.py` — agent with tools that call external systems

```bash
uv run python scripts/choose_pattern.py tool_calling   # or single / supervisor
```

The script deletes the other two stubs and rewires the canonical import in
`agent/agents/__init__.py`. `tests/` and `evals/` import `run_agent`,
`AgentOutput`, `AgentDeps`, and `agent` from that package — never from a stub
module directly — so they keep passing with zero manual edits no matter which
pattern you choose. Run it once, right after cloning.

## Multiple agents

The pattern above is for the app's one *primary* agent. Some apps
legitimately need several independent, differently-shaped agents instead —
e.g. a content-generation app with a "newsletter" agent and a "bluesky_post"
agent, each with its own output schema and instructions, with no shared "one
true agent" identity. That's different from `supervisor.py`: a supervisor
delegating to workers it controls is still one agent from the outside.
Reach for multiple agents when, say, a UI lets a user pick between several
unrelated agents.

Scaffold one with:

```bash
uv run python scripts/add_agent.py newsletter
```

This creates `agent/agents/newsletter.py`, `agent/prompts/newsletter.txt`,
and a smoke test — modeled on the same conventions as the pattern stubs —
without touching `agent/agents/__init__.py`. The canonical re-export there
(`run_agent`, `AgentOutput`, `AgentDeps`, `agent`) stays reserved for the one
primary agent chosen by `choose_pattern.py`. Import each additional agent
directly from its own module wherever you use it:

```python
from agent.agents.newsletter import NewsletterDeps, NewsletterOutput, newsletter_agent, run_newsletter_agent
```

A few things this doesn't automate:

- **Evals** are global today — `evals/test_pass_fail.py` and
  `evals/test_llm_judge.py` both import only the canonical `run_agent`. To
  evaluate an additional agent, copy `evals/fixtures/example.json` to
  `evals/fixtures/newsletter.json` and adapt the two eval files' pattern
  into new files that import `run_newsletter_agent`.
- **The `agent-web-ui` skill** wires its `chat.py` to the canonical
  `from agent.agents import ...` export only. To build a UI over an
  additional agent, point that one import line at the new module instead.

## Usage limits

Each stub defines a `USAGE_LIMITS` constant passed to every run — a guardrail
against runaway agentic loops. `request_limit` caps model round-trips (each
tool-call iteration is one request); `total_tokens_limit` caps overall spend.
Exceeding either raises `UsageLimitExceeded` instead of silently burning
tokens. Tune the values in your chosen stub to fit your task; the supervisor
shares its budget with its workers so the limit bounds the whole delegation
tree.

## Adding tools

Copy `agent/tools/example.py`, implement your tool, register with `@agent.tool`. Use `ModelRetry` only for errors the LLM can fix by changing its input (bad query, out-of-range param) — log and re-raise everything else.

## Customizing the prompt

Edit `agent/prompts/system.txt`. It's loaded via `load_prompt("system")` in `agent/prompts/templates.py`; add more `.txt` files in the same directory and load them the same way.

## Observability

All agent runs, tool calls, and model requests are automatically traced via
`logfire.instrument_pydantic_ai()` — no per-agent setup needed. Cloud vs.
console output is controlled by `LOGFIRE_TOKEN`, see Configuration above.

## Evals

- Pass/fail evals: `evals/test_pass_fail.py` — includes a `pydantic_evals`
  Dataset eval driven by `evals/fixtures/example.json`. Add cases to that JSON
  file to grow the eval; no code changes needed unless a case requires a new
  kind of check (then add an `Evaluator` alongside `ContainsExpected`).
- LLM-as-judge evals: `evals/test_llm_judge.py` — graded by `JUDGE_MODEL`, see Configuration above

Both files share the same `@pytest.mark.eval` marker — there's no separate marker for the LLM-judge subset. `uv run pytest -m eval` runs all of them and requires a real API key; the LLM-judge evals also cost money (they make an extra model call per test to grade the output).

## License

BSD 3-Clause — see [LICENSE](LICENSE).
