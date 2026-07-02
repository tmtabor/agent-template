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
├── config.py         # Settings — validates the provider API key at import time (raises if missing)
├── logging.py         # Logfire setup — configure_logging(), get_logger()
├── agents/            # Three interchangeable stubs — pick one, delete the others
│   ├── single.py       #   one agent, one task (default import target for tests/ and evals/)
│   ├── supervisor.py    #   supervisor delegates to specialized workers
│   └── tool_calling.py  #   agent with tools that call external systems
├── tools/example.py   # Canonical tool pattern — copy and adapt
└── prompts/
    ├── system.txt       # Default system prompt — edit this first
    └── templates.py      # load_prompt() loader

tests/    # Unit tests against TestModel — no API calls, no API key needed
evals/    # Pass/fail + LLM-as-judge evals — real API calls, run with -m eval
```

## Configuration

All settings are read from the environment (see `.env.example`). Key ones:

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | — | Required for whichever provider `MODEL` uses. `Settings` validates this at import time and raises immediately if it's missing — not a lazy/runtime check. |
| `MODEL` | `anthropic:claude-opus-4-8` | The agent under test. Any pydantic-ai model string works, including `ollama:*` for local models (no API key needed). |
| `JUDGE_MODEL` | `anthropic:claude-sonnet-5` | Used only by the LLM-as-judge evals. Kept separate from `MODEL` to avoid self-assessment bias — keep it at least as capable as `MODEL`, not cheaper. |
| `LOGFIRE_TOKEN` | unset | If set, traces go to Logfire cloud. If unset, traces print to the console — no separate dev-mode flag needed. |
| `LOG_LEVEL` | `INFO` | Standard Python logging level. |

## Agent patterns

Three stubs are provided — pick one and delete the others:

- `agent/agents/single.py` — one agent, one task
- `agent/agents/supervisor.py` — supervisor delegates to specialized workers
- `agent/agents/tool_calling.py` — agent with tools that call external systems

Note: `tests/` and `evals/` import from `agent/agents/single.py`. If you delete
it, update those imports to point at the stub you kept.

## Adding tools

Copy `agent/tools/example.py`, implement your tool, register with `@agent.tool`. Use `ModelRetry` only for errors the LLM can fix by changing its input (bad query, out-of-range param) — log and re-raise everything else.

## Customizing the prompt

Edit `agent/prompts/system.txt`. It's loaded via `load_prompt("system")` in `agent/prompts/templates.py`; add more `.txt` files in the same directory and load them the same way.

## Observability

All agent runs, tool calls, and model requests are automatically traced via
`logfire.instrument_pydantic_ai()` — no per-agent setup needed. Cloud vs.
console output is controlled by `LOGFIRE_TOKEN`, see Configuration above.

## Evals

- Pass/fail evals: `evals/test_pass_fail.py`
- LLM-as-judge evals: `evals/test_llm_judge.py` — graded by `JUDGE_MODEL`, see Configuration above
- Add fixtures: `evals/fixtures/`

Both files share the same `@pytest.mark.eval` marker — there's no separate marker for the LLM-judge subset. `uv run pytest -m eval` runs all of them and requires a real API key; the LLM-judge evals also cost money (they make an extra model call per test to grade the output).
