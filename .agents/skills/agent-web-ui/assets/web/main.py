"""FastAPI web UI entry point.

Run with: uv run uvicorn web.main:app --reload --port 8000
"""

from pathlib import Path

import logfire
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agent.logging import configure_logging
from web.routers import chat

configure_logging()

app = FastAPI(title="Agent UI")

# Traces HTTP requests as spans alongside the agent-run spans configure_logging()
# already sets up — so a full request -> agent.run() -> tool calls trace shows
# up as one connected trace in Logfire (or the console, if no token is set).
logfire.instrument_fastapi(app)

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(chat.router)
