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
├── config.py         # Settings — validates the provider API key at import time (raises if missing)
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
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | — | Required for whichever provider `AGENT_MODEL` uses. `Settings` validates this at import time and raises immediately if it's missing — not a lazy/runtime check. |
| `AGENT_MODEL` | `anthropic:claude-opus-4-8` | The agent under test. Any pydantic-ai model string works, including `ollama:*` for local models (no API key needed). |
| `AGENT_JUDGE_MODEL` | `anthropic:claude-sonnet-5` | Used only by the LLM-as-judge evals. Kept separate from `AGENT_MODEL` to avoid self-assessment bias — keep it at least as capable as the agent model, not cheaper. |
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
