"""A conversation: memory across turns, a bounded context window, and streaming.

Use this pattern when:
- Users talk to the agent over several turns and expect it to remember
- The conversation can grow longer than you want to send to the model every time
- The reply should appear as it is generated, not all at once

How it works:
    1. Each turn passes the earlier messages in (`message_history`); the result's messages become the
       next turn's history, so the agent remembers what was said
    2. A history processor keeps only the most recent `max_turns` turns before each model request, so
       cost and context stay bounded. It cuts at turn boundaries, so a tool call is never separated
       from its result
    3. `Conversation` holds the history for you, with `say()` (a full reply and its RunResult) and
       `stream()` (the reply as text deltas)

What this is not: long-term memory. Once a turn falls out of the window the model no longer sees it.
To remember across sessions, store facts yourself and put them in the instructions.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import ProcessHistory, RaiseContentFilterError
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.prompts.templates import load_prompt
from agent.runs import Flow, RunResult

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# Per turn, not per conversation: each call to say() or stream() is bounded by this.
USAGE_LIMITS = UsageLimits(
    request_limit=10, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)


# --- Dependencies ---
@dataclass
class ChatDeps:
    """Runtime dependencies for the chat agent."""

    max_turns: int = 20  # how many of the user's most recent turns the model gets to see

    def __post_init__(self) -> None:
        if self.max_turns < 1:
            raise ValueError("max_turns must be at least 1")


# --- The context window ---
def trim_to_recent_turns(messages: list[ModelMessage], max_turns: int) -> list[ModelMessage]:
    """The last `max_turns` turns of `messages`.

    A turn starts at a request carrying the user's prompt and includes everything after it (the
    reply, any tool calls and their results). Cutting only at turn starts keeps every tool call
    together with its result, which providers require.
    """
    starts = [
        i
        for i, message in enumerate(messages)
        if isinstance(message, ModelRequest)
        and any(isinstance(part, UserPromptPart) for part in message.parts)
    ]
    if len(starts) <= max_turns:
        return messages
    return messages[starts[-max_turns] :]


async def keep_recent_turns(
    ctx: RunContext[ChatDeps], messages: list[ModelMessage]
) -> list[ModelMessage]:
    """The history processor: runs before every model request, using the window from deps."""
    return trim_to_recent_turns(messages, ctx.deps.max_turns)


# --- Agent ---
chat_agent: Agent[ChatDeps, str] = Agent(
    settings.model,
    name=LABEL,
    deps_type=ChatDeps,  # no output_type: plain text, which is also what streams
    capabilities=[RaiseContentFilterError(), ProcessHistory(keep_recent_turns)],
    instructions=load_prompt("conversation"),  # prompts/…; copied to agent/prompts/<name>.txt
)


async def run_chat(
    user_input: str,
    deps: ChatDeps | None = None,
    *,
    history: list[ModelMessage] | None = None,
) -> RunResult[str]:
    """One turn of conversation: reply to `user_input`, given the earlier `history`.

    Returns:
        A RunResult: `.output` is the reply. For the next turn, pass
        `result.steps[0].result.all_messages()` as `history` (`Conversation` does this for you).
    """
    if deps is None:
        deps = ChatDeps()
    logger.info("Chat turn", extra={"user_input": user_input, "history": len(history or [])})
    flow = Flow(USAGE_LIMITS)
    result = await flow.run(chat_agent, user_input, deps=deps, message_history=history)
    return flow.finish(result.output)


@dataclass
class Conversation:
    """A conversation that remembers: holds the history and feeds it back each turn."""

    deps: ChatDeps = field(default_factory=ChatDeps)
    history: list[ModelMessage] = field(default_factory=list)

    async def say(self, text: str) -> RunResult[str]:
        """Send a message and wait for the whole reply."""
        result = await run_chat(text, self.deps, history=self.history)
        self.history = result.steps[0].result.all_messages()
        return result

    async def stream(self, text: str) -> AsyncIterator[str]:
        """Send a message and yield the reply as it is generated, a few words at a time.

        Streaming returns text, not a RunResult; the conversation history is updated once the
        reply is complete, exactly as after `say()`.
        """
        async with chat_agent.run_stream(
            text, deps=self.deps, message_history=self.history, usage_limits=USAGE_LIMITS
        ) as response:
            # debounce_by=None delivers every chunk the provider sends, as it arrives. The default
            # (0.1 s) merges chunks that arrive close together, which suits a UI that repaints;
            # pass a number of seconds here if yours does.
            async for delta in response.stream_text(delta=True, debounce_by=None):
                yield delta
            self.history = response.all_messages()


if __name__ == "__main__":
    import asyncio

    async def demo() -> None:
        conversation = Conversation()
        print(
            (
                await conversation.say("Hi! My name is Priya and I'm planning a trip to Lisbon.")
            ).output
        )
        print((await conversation.say("Which city did I say I was visiting?")).output)
        print("streaming: ", end="")
        async for delta in conversation.stream("And what is my name?"):
            print(delta, end="", flush=True)
        print()

    configure_logging()
    asyncio.run(demo())
