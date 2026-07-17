# CLAUDE.md

This repo is a template: a clean starting point for a production-quality Pydantic AI agent, meant to be cloned and reshaped into a specific agent. The code is the source of truth.

## Commands

```bash
uv sync --group dev            # install deps
uv run pytest                  # unit tests only (TestModel, no API key needed)
uv run pytest -m eval          # all evals — pass/fail AND LLM-judge (needs a real API key, costs money)
uv run ruff check .            # lint
uv run ruff format .           # format
```

There is no separate `llm_judge` marker. Everything in `evals/` carries only `@pytest.mark.eval`, so `-m eval` runs it all in one shot — there's no cheaper eval-only subset to reach for.

`asyncio_mode = "auto"` is set in `pyproject.toml`, so async tests need no `@pytest.mark.asyncio` decorator — don't add them back.

## Making it yours

The intended customization sequence, roughly in order:

1. **Pick a pattern:** `uv run python scripts/choose_pattern.py {single|supervisor|tool_calling}`. It deletes the two unchosen stubs in `agent/agents/` and rewrites the canonical import in `agent/agents/__init__.py`. Tests and evals keep passing with zero manual edits.
2. **Edit the system prompt:** `agent/prompts/system.txt`, loaded via `load_prompt("system")`. Add more `.txt` files beside it and load them the same way.
3. **Define the output schema:** replace the placeholder fields on the output model in your chosen stub. Keep a `result: str` field (or rename it consistently in `evals/`) — it's the canonical field the evals read.
4. **Add tools:** copy the pattern in `agent/tools/example.py`, register with `@agent.tool`.
5. **Tune `USAGE_LIMITS`** in your stub: `request_limit` caps model round-trips per run, `total_tokens_limit` caps spend. The supervisor shares its budget with workers via `usage=ctx.usage`.
6. **Grow the evals:** add cases to `evals/fixtures/example.json` (picked up by the dataset eval in `evals/test_pass_fail.py` automatically) and adapt the judge criteria in `evals/test_llm_judge.py`.

## Non-obvious architecture

- **`agent/config.py` validates at import time, not at call time.** `Settings` has a `model_validator` that raises immediately if the provider implied by `AGENT_MODEL` (`anthropic:`/`openai:` prefix) has no matching API key set. `ollama:` models are exempt — no key required. Agent-specific env vars carry an `AGENT_` prefix; API keys and `LOGFIRE_TOKEN` deliberately don't, because the provider SDKs read those standard names directly. This means `import agent.config` (or anything that imports it transitively) can fail before any code runs, which is the point — but it's also why every module under `agent/` needs *some* key present at import time, even for code paths that never call the model.

- **Unit tests never need real credentials — two layers guarantee it.** `tests/conftest.py` calls `os.environ.setdefault("ANTHROPIC_API_KEY", ...)` / `OPENAI_API_KEY` *before* importing anything from `agent/` (satisfying the import-time validator), and an autouse fixture overrides every `Agent` under `agent.agents` — including nested worker agents — with `TestModel`, so no unit test can ever hit a real model API. Don't remove either — together they're the reason `uv run pytest` works with zero setup and zero spend. `evals/conftest.py` deliberately does **neither**: a missing key there should fail loudly, since evals make real API calls anyway.

- **Tests and evals import canonical names from `agent/agents/__init__.py`** — `run_agent`, `AgentOutput`, `AgentDeps`, `agent` — never from a stub module directly. `scripts/choose_pattern.py` maintains the aliased import line in that file; if you edit it by hand, keep the four canonical names intact. `tests/test_stubs.py` smoke-tests each stub and auto-skips ones the script deleted.

- **Two models, deliberately different.** `settings.model` (default `anthropic:claude-opus-4-8`) is the agent under test; `settings.judge_model` (default `anthropic:claude-sonnet-5`, in `evals/judge.py`) grades its output. They're kept separate to avoid self-assessment bias — but the judge should stay *at least as capable* as the agent, not cheaper/weaker, or the grading itself becomes the unreliable part.

- **Tool error convention:** `ModelRetry` (see `agent/tools/example.py`) is reserved for errors the LLM can plausibly fix by changing its input — bad query format, out-of-range params. Anything else is logged and re-raised as a normal exception. Don't reach for `ModelRetry` as a generic catch-all; it burns the agent's retry budget on failures it has no way to correct.

- **Every run is bounded by `USAGE_LIMITS`.** Exceeding `request_limit` or `total_tokens_limit` raises `UsageLimitExceeded` rather than silently looping. If an agent legitimately needs more iterations, raise the limit in the stub — don't remove the guardrail.

- **Logfire falls back to console automatically** when `LOGFIRE_TOKEN` is unset — there's no separate "dev mode" flag. If you're expecting cloud traces and only seeing console output, check `.env` for the token first.
