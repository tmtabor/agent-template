---
name: macos-launcher
description: Scaffold a native macOS double-clickable launcher (.app with a custom emoji icon) for an agent built from this template — either a web UI (built with the agent-web-ui skill) or a one-shot pipeline agent. Use when asked for a way to launch the agent without a terminal command, a desktop icon, or an .app bundle — macOS only.
metadata:
  version: "1.1.0"
---

# Building a macOS Launcher for This Agent

This skill scaffolds a double-clickable `.app` that runs the agent. It
supports two shapes of agent, controlled by a `RUN_MODE` setting in the
launcher-building script:

- **`web-ui`**: the agent has a persistent web server (built with the
  `agent-web-ui` skill). The launcher starts it and opens a browser tab, plus
  a matching in-UI way to stop it.
- **`pipeline`**: the agent is a one-shot script that fetches/processes/
  delivers something and exits. The launcher runs it once, in the foreground, 
  and keeps the window open with the output visible until you dismiss it.

Either way: no Xcode, Automator, or third-party tools (e.g. Platypus) — the
`.app` is just a plain directory with an `Info.plist`, a shell-script
"executable," and a rendered icon, assembled by a shell script.

This is macOS-only: it relies on `iconutil`, `osascript`, and Terminal.app,
all Apple-specific. Windows/Linux launchers, a designed app-icon template
(squircle background/shadow like stock macOS icons), and a menu-bar or
background-daemon mode are all out of scope for this skill.

## Before you start

Figure out which `RUN_MODE` applies before touching the script:

- **`web-ui`**: the agent needs a web UI already — build one with the
  `agent-web-ui` skill first if it doesn't exist yet. Check for
  `web/main.py`; if it's missing, stop and scaffold the UI before continuing
  here. You'll need the exact command that runs it (the default from
  `agent-web-ui` is `uv run uvicorn web.main:app --port 8000`) and the port,
  since both get baked into the launcher script below.
- **`pipeline`**: no `agent-web-ui` dependency at all. You just need a
  one-shot command that already runs correctly from a terminal — e.g.
  `uv run python scripts/run_pipeline.py` or `uv run python -m agent.pipeline.run`,
  whatever this agent's own entrypoint is. Confirm it actually works from a
  plain terminal in the repo root before wiring it into the launcher.

  One thing worth flagging either way, but especially here: if this agent
  also runs on a schedule via CI, that CI run gets its API keys/secrets from
  the CI environment, not from this repo's `.env`. Double-clicking the
  launcher only has access to `.env` — confirm it's populated locally with
  everything the pipeline needs before assuming the launcher is broken.

## What to build

Copy `assets/scripts/` into the repo root as `scripts/` (alongside
`scripts/choose_pattern.py` if it's already there):

```
scripts/
├── build_launcher.sh          # assembles and installs the .app
└── render_emoji_icon.py       # renders an emoji to a .icns icon
```

`render_emoji_icon.py` needs no changes — it's fully generic, taking the
emoji and output path as CLI arguments. Read it in full before copying,
don't summarize and re-generate from memory: the inline comments (why a
padded probe canvas + `Image.getbbox()` is used instead of `textbbox()` to
find the glyph's real extent, why one master render is downscaled to every
size rather than re-rendering per size) matter if it's later modified.

`build_launcher.sh` ships with template defaults and needs these things
adapted to the actual agent:

- `APP_NAME="Agent UI"` — the display name shown under the Dock icon and in
  `~/Applications`
- The emoji passed to `render_emoji_icon.py` (currently `"🤖"`) — pick
  something that reads at 16px, since that's the smallest rendered size
- `CFBundleIdentifier` (currently `com.example.agent-launcher`) — a real
  reverse-DNS identifier, e.g. `com.yourname.your-agent-launcher`
- `RUN_MODE` — `"web-ui"` or `"pipeline"`, per **Before you start** above.
  This picks which of the two `Contents/MacOS/launcher` bodies gets written;
  everything else below applies to both.
- `ENTRY_CMD` — the actual run command, e.g. `uv run uvicorn web.main:app --port 8000`
  for `web-ui` mode or `uv run python scripts/run_pipeline.py` for `pipeline`
  mode. This is the one thing both modes share — whatever the command is,
  it's the only place it needs to be set.
- `web-ui` mode only: the `open "http://localhost:8000"` line — keep the
  port in sync with whatever `ENTRY_CMD` above uses. `pipeline` mode has no
  equivalent line since there's no server to open a browser tab against.

## Adding a clean way to stop it (`web-ui` mode only)

Skip this section entirely for `pipeline` mode — there's nothing long-running
to stop. The launcher's finish-and-pause line (`echo; echo Run finished. ...;
read`) already keeps the output on screen until you dismiss it, whether the
run succeeded or failed, and the process exits on its own either way.

For `web-ui` mode, starting and stopping cleanly is one feature, not two —
add both together. Ctrl+C in the launcher's Terminal window already stops
the server cleanly (the launcher runs it in the foreground via `exec`), but
add an in-UI alternative too, since not everyone wants to touch the
terminal.

**1. Add a shutdown route to `web/main.py`:**

```python
import asyncio
import os
import signal

from fastapi.responses import HTMLResponse


@app.post("/shutdown", response_class=HTMLResponse)
async def shutdown() -> HTMLResponse:
    """Stop the server from the UI — an alternative to Ctrl+C in the launcher's terminal."""

    async def _stop() -> None:
        await asyncio.sleep(0.3)  # let this response finish sending first
        os.kill(os.getpid(), signal.SIGINT)  # same signal Ctrl+C sends; uvicorn shuts down cleanly

    asyncio.create_task(_stop())
    return HTMLResponse("<p>Shutting down — you can close this tab and the terminal window.</p>")
```

The 0.3s delay before the signal matters: sending `SIGINT` immediately can
race the response being flushed to the client, so the browser sees a
connection-reset instead of the confirmation message.

**2. Add a shutdown link to `web/templates/base.html`'s sidebar** (adjust
the markup to fit the existing sidebar structure — the important parts are
the form action and the confirm guard):

```html
<form
  method="post"
  action="/shutdown"
  class="sidebar-shutdown"
  onsubmit="return confirm('Shut down the server?');"
>
  <button type="submit" class="sidebar-danger-link">Shut down server</button>
</form>
```

**3. Add matching CSS to `web/static/app.css`**, pinned to the bottom of
the sidebar:

```css
/* .sidebar is a flex column; margin-top: auto pushes this to the end
   regardless of how much nav content is above it. */
.sidebar-shutdown {
  margin-top: auto;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.sidebar-danger-link {
  display: block;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: var(--radius);
  background: none;
  color: #f38ba8;
  text-decoration: none;
  font-size: 0.9rem;
  font: inherit;
  cursor: pointer;
  text-align: left;
}
```

## Building and installing

```bash
bash scripts/build_launcher.sh
```

This renders the icon, assembles the `.app` bundle in a temp directory, and
installs it to `~/Applications`. Safe to re-run any time — it overwrites the
previous build, so re-running after changing the emoji, app name, or entry
command is the way to pick up those changes.

## Verify it actually works

Double-click the installed `.app` from `~/Applications` (or Spotlight).

**`web-ui` mode**, confirm:

- A Terminal window opens and the server starts in the foreground
- A browser tab opens automatically a couple seconds later, pointed at the
  right port
- Ctrl+C in that terminal stops the server cleanly (no traceback, uvicorn's
  normal shutdown log lines)
- Separately, clicking the in-UI "Shut down server" link also stops the
  server — check the terminal shows the same clean uvicorn shutdown, not a
  hang or an unhandled exception

**`pipeline` mode**, confirm:

- A Terminal window opens and `ENTRY_CMD` runs to completion with its normal
  output visible (same log lines you'd see running it by hand, or watching
  the equivalent CI job)
- The "Run finished. Press Return to close this window." prompt appears
  once the command exits, and pressing Return closes the window
- A failing run (a bad `.env` value is an easy way to force one) still shows
  the error output and the same prompt, rather than the window disappearing
  before the failure is readable
