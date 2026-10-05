"""Chat endpoints: render the page, then handle each turn via an HTMX partial swap.

Serves ONE agent. The template has no canonical agent, so point the import
below at the module of the agent this UI should serve (see SKILL.md, "Before
you start"). It is aliased to the generic names `agent`, `AgentDeps` and
`USAGE_LIMITS` so the rest of this file never changes.

Uses agent.run() directly instead of the higher-level run_agent() helper
because run_agent() doesn't accept message_history= — multi-turn chat needs
that, so this router takes on usage_limits= itself instead.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic_ai import UsageLimitExceeded
from pydantic_ai.exceptions import ContentFilterError

# TODO: replace `triage` and the names with the agent this UI serves.
from agent.agents.triage import USAGE_LIMITS, SharedDeps as AgentDeps, supervisor_agent as agent
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
    except ContentFilterError:
        return _render(
            request,
            session_id,
            "partials/message_pair.html",
            {
                "user_message": message,
                "agent_message": "I can't help with that request — try rephrasing it.",
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

    # The example agents' output types keep a `result: str` field by convention (see
    # AGENTS.md's "Making it yours" section) — read it directly rather than
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
