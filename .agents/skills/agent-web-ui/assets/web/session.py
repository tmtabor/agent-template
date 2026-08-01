"""In-memory, cookie-keyed chat session store.

One process, one browser tab's worth of state per session — matches this
template's local-first, no-database philosophy. Swap `_store` for Redis or a
DB only if you actually need multi-worker/multi-instance deployment; don't
add that complexity preemptively.
"""

import secrets
import time
from dataclasses import dataclass, field

from fastapi import Request, Response
from pydantic_ai.messages import ModelMessage

SESSION_COOKIE = "agent_session"
SESSION_TTL_SECONDS = 3600


@dataclass
class ChatSession:
    # Passed back into agent.run(message_history=...) on every turn — this is
    # the actual conversational memory. Use all_messages(), not
    # new_messages(), when updating it after a run (see agent/agents/*.py's
    # "Multi-turn conversation example" comment) or you'll silently drop
    # earlier turns.
    history: list[ModelMessage] = field(default_factory=list)

    # Rendered {"role": ..., "text": ...} turns for the template to loop over.
    # Kept separate from `history` because ModelMessage internals differ by
    # output_type (structured output goes through a tool-call part, not a
    # plain TextPart) — reconstructing display text from raw message parts is
    # fragile, so the router appends here directly instead.
    turns: list[dict] = field(default_factory=list)

    last_seen: float = field(default_factory=time.time)


_store: dict[str, ChatSession] = {}


def _purge_expired() -> None:
    now = time.time()
    expired = [sid for sid, s in _store.items() if now - s.last_seen > SESSION_TTL_SECONDS]
    for sid in expired:
        del _store[sid]


def get_or_create_session(request: Request) -> tuple[str, ChatSession]:
    """Look up the caller's session by cookie, creating one if absent.

    Returns `(session_id, session)`. Deliberately doesn't touch cookies
    itself — call `attach_session_cookie(response, session_id)` on whatever
    response object the route actually returns. FastAPI does NOT merge
    cookies set on an injected `Response` parameter into a Response you
    construct and return yourself (a `TemplateResponse`, a redirect, ...);
    doing it here on a throwaway Response would set a Set-Cookie header that
    never reaches the client — a real, easy-to-miss FastAPI gotcha, not a
    simplification.
    """
    _purge_expired()
    session_id = request.cookies.get(SESSION_COOKIE)
    session = _store.get(session_id) if session_id else None

    if session is None:
        session_id = secrets.token_urlsafe(24)
        session = ChatSession()
        _store[session_id] = session

    session.last_seen = time.time()
    return session_id, session


def attach_session_cookie(response: Response, session_id: str) -> None:
    """Set/refresh the session cookie on the response object being returned.

    Called on every response, not just new sessions — this also refreshes
    the cookie's max_age on each turn, so an active conversation doesn't
    expire mid-use.
    """
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
    )
