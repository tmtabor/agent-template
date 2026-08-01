# Optional: token-by-token streaming

The default chat pattern in `SKILL.md` calls `agent.run()` and swaps in the
full reply once it's ready — HTMX shows a spinner while the request is in
flight (see `.htmx-request .spinner` in `app.css`). This works for *any*
`output_type`, including the structured `AgentOutput` models this template's
stubs use by default, and it's the right default: it's simpler, has fewer
moving parts, and doesn't force a choice on output type.

Reach for real token streaming only when the user specifically wants the
"live typing" feel — e.g. they're building a long-form assistant where
waiting several seconds for a full reply feels bad. Bring it up as a
trade-off rather than defaulting to it: streaming only works cleanly when
`output_type=str` (or you're willing to stream partial structured output via
`stream_structured()`, which is more involved — see the Pydantic AI docs for
`Agent.run_stream`).

## Why structured output complicates streaming

`agent.run_stream()` + `stream_text(delta=True)` yields plain text deltas.
That's a natural fit when the agent's `output_type` is `str`. But this
template's stubs default to a structured `AgentOutput` (with a `result: str`
field) produced via tool-call-style structured output — there's no plain
text delta stream to read from in that case. Either:

- Change the agent's `output_type` to `str` for the UI-facing agent (fine if
  you don't need the other fields — e.g. `confidence` — outside evals), or
- Use `stream_structured()` and read partial `.result` values off the
  in-progress model as it validates — more code, and the partial object may
  not have `result` populated until later in the stream.

The rest of this doc assumes `output_type=str`.

## SSE endpoint (server side)

Add a second route alongside `POST /chat` — don't replace it, since the
non-streaming path is still useful as a fallback and for testing:

```python
import asyncio

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from agent.agents import USAGE_LIMITS, AgentDeps, agent
from web.session import get_or_create_session

router = APIRouter()


@router.get("/chat/stream")
async def chat_stream(request: Request, response: Response, message: str) -> StreamingResponse:
    session = get_or_create_session(request, response)

    async def event_source():
        full_reply = ""
        try:
            async with agent.run_stream(
                message,
                deps=AgentDeps(),
                message_history=session.history,
                usage_limits=USAGE_LIMITS,
            ) as stream:
                async for chunk in stream.stream_text(delta=True):
                    full_reply += chunk
                    yield f"event: token\ndata: {chunk}\n\n"
                session.history = stream.all_messages()
        except Exception:
            yield "event: error\ndata: Something went wrong on my end.\n\n"
            return

        session.turns.append({"role": "user", "text": message})
        session.turns.append({"role": "assistant", "text": full_reply})
        yield "event: done\ndata: \n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
```

A few things worth calling out:

- **Newlines in a chunk break SSE framing** — an SSE `data:` line can't
  contain a literal `\n` inside a single field without special handling.
  Either send each chunk as its own frame (as above — fine for chat-sized
  deltas) or `json.dumps()` the chunk so newlines get escaped, and
  `JSON.parse()` it client-side.
- **`asyncio.Queue` + a background task**, not a bare async generator, if you
  need to push non-text events (e.g. "tool X is running…" status updates)
  onto the same stream from inside a `@agent.tool` function. Use a
  `contextvars.ContextVar[asyncio.Queue]` set before the run starts and read
  from inside the tool — this lets any tool push a human-readable status
  string onto the same queue the text deltas are flowing through, without
  instrumenting every tool call site individually.

## Client side: hand-rolled SSE parser

`EventSource` doesn't let you send a request body or control credentials the
way a POST-based chat turn needs, so use `fetch` + `ReadableStream` instead of
the built-in `EventSource` API. Add this as an inline `<script>` in
`index.html` (no separate `.js` file, no build step — consistent with the
rest of this pattern):

```html
<script>
async function sendMessage(message) {
  const messagesEl = document.getElementById('chat-messages');
  const bubble = document.createElement('div');
  bubble.className = 'message assistant streaming';
  bubble.innerHTML = '<div class="bubble"></div>';
  messagesEl.appendChild(bubble);
  const bubbleText = bubble.querySelector('.bubble');

  const response = await fetch(`/chat/stream?message=${encodeURIComponent(message)}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let frameEnd;
    while ((frameEnd = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, frameEnd);
      buffer = buffer.slice(frameEnd + 2);
      const [eventLine, dataLine] = frame.split('\n');
      const event = eventLine.replace('event: ', '');
      const data = (dataLine || '').replace('data: ', '');

      if (event === 'token') {
        bubbleText.textContent += data;
        messagesEl.scrollTop = 1e9;
      } else if (event === 'error') {
        bubbleText.textContent = data;
        bubble.classList.add('error');
      } else if (event === 'done') {
        bubble.classList.remove('streaming');
      }
    }
  }
}
</script>
```

Pair this with a `.streaming` CSS class that shows an animated cursor
(`::after { content: "▮"; animation: blink 1s step-end infinite; }`),
removed once the `done` event lands.
