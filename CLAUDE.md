# CLAUDE.md

Guidance for working in this repo day-to-day. For the full from-scratch build rationale (why each file exists, the exact original spec), see `IMPLEMENTATION_GUIDE.md` — don't duplicate its contents here, and don't treat it as current documentation; the code is the source of truth.

## Commands

```bash
uv sync --group dev            # install deps
uv run pytest                  # unit tests only (TestModel, no API key needed)
uv run pytest -m eval          # all evals — pass/fail AND LLM-judge (needs a real API key, costs money)
uv run ruff check .            # lint
uv run ruff format .           # format
```

There is no separate `llm_judge` marker. `evals/test_pass_fail.py` and `evals/test_llm_judge.py` both carry only `@pytest.mark.eval`, so `-m eval` runs everything in `evals/` in one shot — there's no cheaper eval-only subset to reach for.

## Non-obvious architecture

- **`agent/config.py` validates at import time, not at call time.** `Settings` has a `model_validator` that raises immediately if the provider implied by `MODEL` (`anthropic:`/`openai:` prefix) has no matching API key set. `ollama:` models are exempt — no key required. This means `import agent.config` (or anything that imports it transitively) can fail before any code runs, which is the point — but it's also why every module under `agent/` needs *some* key present at import time, even for code paths that never call the model.

- **Unit tests never need real credentials.** `tests/conftest.py` calls `os.environ.setdefault("ANTHROPIC_API_KEY", ...)` / `OPENAI_API_KEY` *before* importing anything from `agent/`, specifically to satisfy the config validator above. `setdefault` means a real key in the environment is never overwritten. Don't remove this — it's the reason `uv run pytest` works with zero setup. `evals/conftest.py` deliberately does **not** do this: a missing key there should fail loudly, since evals make real API calls anyway.

- **`tests/` and `evals/` both import `run_agent` (and `AgentOutput`/`AgentDeps`) from `agent/agents/single.py`.** The three agent stubs (`single.py`, `supervisor.py`, `tool_calling.py`) are meant as alternatives — pick one, delete the others — but if you delete `single.py`, you must also update the imports in `tests/test_example.py`, `evals/test_pass_fail.py`, and `evals/test_llm_judge.py` to point at whichever stub you kept.

- **Two models, deliberately different.** `settings.model` (default `anthropic:claude-opus-4-8`) is the agent under test; `settings.judge_model` (default `anthropic:claude-sonnet-5`, in `evals/judge.py`) grades its output. They're kept separate to avoid self-assessment bias — but the judge should stay *at least as capable* as the agent, not cheaper/weaker, or the grading itself becomes the unreliable part.

- **Tool error convention:** `ModelRetry` (from `agent/tools/example.py`, `agent/agents/tool_calling.py`) is reserved for errors the LLM can plausibly fix by changing its input — bad query format, out-of-range params. Anything else is logged and re-raised as a normal exception. Don't reach for `ModelRetry` as a generic catch-all; it burns the agent's retry budget on failures it has no way to correct.

- **Logfire falls back to console automatically** when `LOGFIRE_TOKEN` is unset — there's no separate "dev mode" flag. If you're expecting cloud traces and only seeing console output, check `.env` for the token first.

## Don't add

These were deliberately left out of the template; suggesting them back in usually means re-reading `IMPLEMENTATION_GUIDE.md`'s "Do not add" rationale first: a `Makefile`, `docker-compose.yml`, a `main.py` entry point (each stub has its own `if __name__ == "__main__":`), a `base.py` for agents, a `memory/` directory (message history is handled via `message_history=`), MCP server scaffolding, or a dedicated web-search module (it's `capabilities=[WebSearch()]` on the agent, not a file).
