---
name: agent-web-ui
description: Scaffold a local web UI (chat interface, dashboard, or multi-step wizard) for a Pydantic AI agent built from this template — FastAPI + Jinja2 + HTMX, zero JS build step. Use whenever asked to build a UI, web interface, chat UI, or dashboard for this agent, or to add a way to interact with the agent from a browser — even if the user doesn't name a specific stack, since this skill supplies the house default.
metadata:
  version: "1.0.0"
---

# Building a Web UI for This Agent

This skill scaffolds a local web UI for an agent built from this template:
FastAPI + Jinja2 + HTMX, no npm, no build step. This is the house pattern for
this template — follow it so agent UIs built from this template stay
recognizable to each other instead of every one reinventing its own frontend.

## Why this stack, not a JS framework

No React, Vue, or bundler. The reasons:

- These are **local-first, single-user tools**, not multi-tenant products. A
  build pipeline, package.json, and node_modules buy nothing here.
- **Same-origin, same-process deployment**: `uvicorn web.main:app` is the
  entire deploy story. No separate frontend build/deploy, no CORS.
- **The agent's real output is server-side Python already** — Pydantic
  models, tool results, `ModelMessage` history. Rendering that as HTML on the
  server and patching the DOM with HTMX avoids a duplicate
  serialize-to-JSON / re-parse-in-JS round trip for state that already lives
  in Python.

Don't second-guess this by reaching for React because it's more familiar —
match the house style unless the user explicitly asks for something else.

## Before you start

1. **A pattern must already be chosen.** Check `ls agent/agents/*.py` — if
   you see all three of `single.py`, `supervisor.py`, `tool_calling.py`, a
   pattern hasn't been picked yet. Run
   `uv run python scripts/choose_pattern.py {single|supervisor|tool_calling}`
   first (ask the user which, if unclear). Building the UI against
   `agent.agents`' canonical names works regardless of pattern, but do this
   first anyway — it's a prerequisite of the template itself, and doing it
   after hand-editing `agent/agents/__init__.py` (step 2 below) will fail the
   script's exact-match check.

2. **Export `USAGE_LIMITS` alongside the other canonical names.** Every
   stub defines a module-level `USAGE_LIMITS` constant, but
   `agent/agents/__init__.py` only re-exports `AgentDeps`, `AgentOutput`,
   `agent`, `run_agent` today. The UI needs `agent.run()` directly (not the
   `run_agent()` helper — it doesn't accept `message_history=`, which
   multi-turn chat needs), so it needs `USAGE_LIMITS` too, or every chat
   turn runs unbounded, silently dropping the guardrail CLAUDE.md calls out
   as load-bearing. Add it to the existing import line and `__all__`, e.g.
   for the single-agent pattern:

   ```python
   from agent.agents.single import USAGE_LIMITS, AgentDeps, AgentOutput, agent, run_agent

   __all__ = ["USAGE_LIMITS", "AgentDeps", "AgentOutput", "agent", "run_agent"]
   ```

   This is safe to hand-edit at this point — `choose_pattern.py` won't run
   again once the other two stubs are deleted (it exits early with "already
   chosen" otherwise).

3. **Check the output type's `result` field.** Every stub's output model
   keeps a `result: str` field by convention (see CLAUDE.md's "Making it
   yours" section). The chat router below reads `result.output.result`
   directly — if the field was renamed, either rename it back, adjust the
   router, or confirm `output_type=str` (in which case the router's
   `hasattr` fallback handles it already).

## What to build

Copy `assets/web/` into the repo root as `web/`, sibling to `agent/`,
`evals/`, `tests/`:

```
web/
├── main.py                       # FastAPI() app, mounts static, wires routers
├── session.py                    # in-memory cookie-keyed ChatSession store
├── routers/
│   ├── __init__.py
│   └── chat.py                   # GET "/" and POST "/chat"
├── templates/
│   ├── base.html                 # sidebar shell + htmx CDN tag
│   ├── index.html                # chat page
│   └── partials/
│       └── message_pair.html     # user+assistant bubble pair (htmx swap target)
└── static/
    └── app.css                   # dark-sidebar/light-content design tokens
```

Copy the files as-is first, then adapt:

- **`session.py`**: usually needs no changes — it's deliberately generic.
- **`routers/chat.py`**: adjust the `deps=AgentDeps()` call if your `AgentDeps`
  dataclass has required fields (the default stub has none).
- **`templates/base.html`**: add sidebar nav links here as you add more pages
  (a settings page, a session list, a status dashboard — whatever the agent
  needs beyond chat).
- **`static/app.css`**: the `:root` custom properties are the whole palette —
  restyle by changing values there, not by scattering new colors through the
  rest of the file. Keep the `.card` / `.spinner`+`.btn-text` idioms if you
  add more HTMX-driven views; they're the reusable primitives, not
  chat-specific.

Read each asset file in full before copying — don't summarize and
re-generate from memory, the inline comments carry decisions (why history
and turns are stored separately, why the `hasattr` fallback exists, why the
session cookie is attached to the response each route actually returns
rather than to an injected `Response` parameter) that matter if you later
modify the file.

## Wiring it up

1. **Add dependencies** — this template has no web dependencies yet:

   ```bash
   uv add fastapi jinja2 python-multipart "uvicorn[standard]"
   uv add "logfire[fastapi]"
   ```

   The second command matters and is easy to skip: `agent/logging.py`'s
   `configure_logging()` already sets up Logfire for the agent, but
   `logfire.instrument_fastapi(app)` in `web/main.py` additionally needs the
   `opentelemetry-instrumentation-fastapi` package, which only
   `logfire[fastapi]` (not the bare `logfire>=3.0` already in
   `pyproject.toml`) pulls in. Without it the app raises `RuntimeError` on
   startup, not on first request — so this fails immediately and loudly if
   skipped, but confirm it either way rather than assuming.

   Add these to the main `[project.dependencies]` in `pyproject.toml`, not
   the `dev` group — the UI is a shipped part of the app, not a dev tool.

2. **Run it**:

   ```bash
   uv run uvicorn web.main:app --reload --port 8000
   ```

   No Docker, no separate build step — deployment is just
   `uvicorn <app>:app` and nothing else. Don't add a Dockerfile or
   deployment manifest unless asked; it's out of scope for what's being
   requested here.

3. **Verify it actually works** — start the server and drive it in a
   browser (or via `curl`/`httpx` against `POST /chat` if no browser is
   available) before calling this done. Confirm: a fresh page load shows the
   empty state, sending a message shows the spinner then the reply, a second
   message correctly carries conversation context (proves `message_history`
   round-trips through the session), and reloading the page replays prior
   turns from `session.turns`.

   Pay particular attention to the session cookie actually being set
   (`curl -i` and check for a `set-cookie` header, or check dev tools'
   Application/Storage tab in a browser) — if you restructure `chat.py`'s
   routes while adapting them, it's easy to reintroduce the bug this
   pattern is built to avoid: FastAPI silently drops cookies set on an
   injected `Response` parameter if the route returns a different Response
   object (a `TemplateResponse`, here) instead of using that parameter. The
   symptom is subtle — every request looks like a brand-new session, so
   conversation context never persists, but each individual response still
   looks fine in isolation.

## Multi-turn state: how it fits together

`web/session.py`'s `ChatSession.history` holds the raw `list[ModelMessage]`
that Pydantic AI itself produces — the same object `result.all_messages()`
returns. This is the idiomatic "engine-native" state pattern both reference
projects use: don't invent your own chat-log schema and reconstruct
`message_history=` from it. Store what Pydantic AI gives you, pass it back
unchanged.

`ChatSession.turns` is a separate, UI-only list of `{"role", "text"}` dicts
used purely for rendering. Keeping it separate from `history` avoids a real
trap: reconstructing display text by walking `ModelMessage` parts breaks for
structured output, since a structured `AgentOutput` is produced via a
tool-call part, not a plain `TextPart` — there's no reliable generic way to
pull "the text" back out of history after the fact. Appending to `turns`
directly, right where you already have `reply_text` computed, sidesteps the
whole problem.

## Extending beyond chat

If the agent needs more than a single chat surface — a multi-step wizard
(data-collection form → generate → review → publish), a dashboard, or a
status page — the same primitives extend cleanly:

- **Wizard / multi-step flows**: model each stage as a field on a per-session
  dataclass (like `ChatSession`, but with a `stage: str` field and
  stage-specific data), and swap `{% if stage == "..." %}` blocks in one
  template — the server decides what to render based on session state,
  there's no client-side routing to build. Each stage transition is an
  `hx-post` that returns the freshly-rendered fragment for
  `hx-swap="outerHTML"`.
- **Long-running steps**: if a step takes longer than a few seconds, don't
  block the HTMX request — kick off the work, have the endpoint return
  immediately with a polling placeholder, and add a lightweight `GET
  /status` endpoint that a `setInterval` polls (started on
  `htmx:beforeRequest`, stopped on `htmx:afterSettle`) to show live progress
  text. This is simpler to get right than SSE for one-shot, non-chat steps.
- **Exposing which tool is running**: for a supervisor pattern where you want
  to surface "worker X is now handling this" in the UI, a
  `contextvars.ContextVar[asyncio.Queue]` set before the run and read inside
  `@agent.tool` functions is the reusable technique — see
  `references/STREAMING.md` for the concrete pattern (it's written for SSE
  but the ContextVar trick applies equally to a polling-based status
  endpoint).
- **Token-by-token streaming chat**: only if specifically requested, and only
  cleanly compatible with `output_type=str`. See `references/STREAMING.md`
  before implementing — it covers why structured output complicates this and
  what changes on both the server and client side.

## Testing

Use FastAPI's `TestClient` with `raise_server_exceptions=False`, plus an
autouse fixture clearing
`web.session._store` between tests so sessions don't leak across test cases.
This template's `tests/conftest.py` already overrides every `Agent` under
`agent.agents` with `TestModel` — that override applies automatically to the
`agent` object `web/routers/chat.py` imports too, so UI tests get the same
"no real API calls" guarantee as everything else without extra setup.
