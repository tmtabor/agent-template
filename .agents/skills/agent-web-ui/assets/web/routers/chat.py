"""Chat endpoints: render the page, then handle each turn via an HTMX partial swap.

Imports the canonical `agent`, `AgentDeps`, `USAGE_LIMITS` names from
`agent.agents` rather than a concrete stub module — this keeps working
regardless of which pattern `scripts/choose_pattern.py` picked. USAGE_LIMITS
isn't re-exported by default; add it alongside the other four names in
agent/agents/__init__.py (see SKILL.md step 2) before this import works.

Uses agent.run() directly instead of the higher-level run_agent() helper
because run_agent() doesn't accept message_history= — multi-turn chat needs
that, so this router takes on usage_limits= itself instead.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic_ai import UsageLimitExceeded

from agent.agents import USAGE_LIMITS, AgentDeps, agent
from agent.logging import get_logger
from web.session import attach_session_cookie, get_or_create_session

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")
logger = get_logger(__name__)


def _render(request: Request, session_id: str, template: str, context: dict) -> HTMLResponse:
    """Render a template and attach the session cookie to that exact response.

    Centralizing this matters: attach_session_cookie() must be called on the
    literal object being returned (see web/session.py's docstring for why),
    and chat() below has three separate return points.
    """
    response = templates.TemplateResponse(request, template, context)
    attach_session_cookie(response, session_id)
    return response


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    session_id, session = get_or_create_session(request)
    return _render(request, session_id, "index.html", {"turns": session.turns})


@router.post("/chat", response_class=HTMLResponse)
async def chat(request: Request, message: str = Form(...)) -> HTMLResponse:
    session_id, session = get_or_create_session(request)

    try:
        result = await agent.run(
            message,
            deps=AgentDeps(),
            message_history=session.history,
            usage_limits=USAGE_LIMITS,
        )
    except UsageLimitExceeded:
        return _render(
            request,
            session_id,
            "partials/message_pair.html",
            {
                "user_message": message,
                "agent_message": "This conversation hit its usage limit — start a new one.",
                "error": True,
            },
        )
    except Exception:
        logger.exception("Agent run failed")
        return _render(
            request,
            session_id,
            "partials/message_pair.html",
            {
                "user_message": message,
                "agent_message": "Something went wrong on my end — please try again.",
                "error": True,
            },
        )

    session.history = result.all_messages()

    # Every stub's output type keeps a `result: str` field by convention (see
    # CLAUDE.md's "Making it yours" section) — read it directly rather than
    # str()-ing the whole output model, which would dump every field
    # (confidence, etc.) into the chat bubble. Falls back to str() for a
    # plain `output_type=str` agent, which has no `.result` attribute.
    reply_text = result.output.result if hasattr(result.output, "result") else str(result.output)

    session.turns.append({"role": "user", "text": message})
    session.turns.append({"role": "assistant", "text": reply_text})

    return _render(
        request,
        session_id,
        "partials/message_pair.html",
        {"user_message": message, "agent_message": reply_text},
    )
