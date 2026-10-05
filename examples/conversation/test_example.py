"""The window, the history it keeps, and streaming — offline, with scripted models."""

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from examples.conversation.agent import (
    ChatDeps,
    Conversation,
    chat_agent,
    keep_recent_turns,
    run_chat,
    trim_to_recent_turns,
)

# --- The window ---


def turn(n: int) -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart(f"q{n}")]),
        ModelResponse(parts=[TextPart(f"a{n}")]),
    ]


def conversation_of(count: int) -> list[ModelMessage]:
    return [message for n in range(1, count + 1) for message in turn(n)]


def prompts(messages: list[ModelMessage]) -> list[str]:
    return [
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]


def test_a_conversation_within_the_window_is_untouched():
    messages = conversation_of(3)
    assert trim_to_recent_turns(messages, 3) is messages
    assert trim_to_recent_turns(messages, 10) is messages


def test_only_the_most_recent_turns_are_kept():
    assert prompts(trim_to_recent_turns(conversation_of(5), 2)) == ["q4", "q5"]
    assert prompts(trim_to_recent_turns(conversation_of(5), 1)) == ["q5"]


def test_the_window_starts_at_a_users_prompt_never_mid_turn():
    kept = trim_to_recent_turns(conversation_of(4), 2)
    assert isinstance(kept[0], ModelRequest) and prompts(kept)[0] == "q3"
    assert len(kept) == 4  # two whole turns: a request and a reply each


def test_a_tool_call_stays_with_its_result_because_the_whole_turn_is_one_unit():
    with_tool = [
        ModelRequest(parts=[UserPromptPart("look it up")]),
        ModelResponse(parts=[ToolCallPart("lookup", {"q": "x"}, tool_call_id="c1")]),
        ModelRequest(
            parts=[ToolReturnPart("lookup", "found", tool_call_id="c1")]
        ),  # no user prompt
        ModelResponse(parts=[TextPart("here it is")]),
    ]
    messages = [*conversation_of(2), *with_tool]
    kept = trim_to_recent_turns(messages, 1)
    assert kept == with_tool  # the tool-return request did not start a new "turn"


def test_an_empty_history_is_fine():
    assert trim_to_recent_turns([], 3) == []


@pytest.mark.parametrize("bad", [0, -1])
def test_a_window_smaller_than_one_turn_is_rejected(bad):
    with pytest.raises(ValueError, match="at least 1"):
        ChatDeps(max_turns=bad)


def test_the_default_window_is_twenty_turns():
    assert ChatDeps().max_turns == 20


async def test_the_processor_reads_the_window_from_deps():
    ctx = RunContext(deps=ChatDeps(max_turns=1), model=TestModel(), usage=RunUsage())
    assert prompts(await keep_recent_turns(ctx, conversation_of(3))) == ["q3"]


# --- Remembering, with a scripted model ---


def echo_model(seen: list[list[ModelMessage]]):
    """Replies `reply N` and records the messages each request carried."""

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        seen.append(list(messages))
        return ModelResponse(parts=[TextPart(f"reply {len(seen)}")])

    return FunctionModel(model_fn)


async def test_a_turn_with_no_history_sees_only_itself():
    seen: list = []
    with chat_agent.override(model=echo_model(seen)):
        result = await run_chat("hello")
    assert prompts(seen[0]) == ["hello"] and result.output == "reply 1"


async def test_history_passed_in_is_what_the_model_sees():
    seen: list = []
    with chat_agent.override(model=echo_model(seen)):
        first = await run_chat("my name is Priya")
        await run_chat("what is my name?", history=first.steps[0].result.all_messages())
    assert prompts(seen[1]) == ["my name is Priya", "what is my name?"]


async def test_a_conversation_remembers_every_turn():
    seen: list = []
    conversation = Conversation()
    with chat_agent.override(model=echo_model(seen)):
        for text in ("one", "two", "three"):
            await conversation.say(text)
    assert prompts(seen[2]) == ["one", "two", "three"]
    assert prompts(conversation.history) == ["one", "two", "three"]


async def test_the_window_limits_what_the_model_sees_and_what_is_kept():
    seen: list = []
    conversation = Conversation(ChatDeps(max_turns=2))
    with chat_agent.override(model=echo_model(seen)):
        for text in ("one", "two", "three", "four"):
            await conversation.say(text)
    assert prompts(seen[3]) == ["three", "four"]  # "one" and "two" fell out of the window
    assert "one" not in prompts(conversation.history)


async def test_say_returns_a_run_result_for_the_turn():
    with chat_agent.override(model=echo_model([])):
        result = await Conversation().say("hi")
    assert [step.agent for step in result.steps] == ["conversation"] and result.output == "reply 1"


# --- Streaming ---


def streaming_model(chunks: list[str], seen: list[list[ModelMessage]]):
    async def stream_fn(messages, info: AgentInfo):
        seen.append(list(messages))
        for chunk in chunks:
            yield chunk

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        seen.append(list(messages))
        return ModelResponse(parts=[TextPart("".join(chunks))])

    return FunctionModel(model_fn, stream_function=stream_fn)


async def test_a_reply_streams_as_chunks_that_add_up_to_the_whole_reply():
    chunks = ["Hello, ", "Priya", "!"]
    conversation = Conversation()
    with chat_agent.override(model=streaming_model(chunks, [])):
        received = [delta async for delta in conversation.stream("hi")]
    assert received == chunks
    final = conversation.history[-1]
    assert isinstance(final, ModelResponse) and final.parts[0].content == "Hello, Priya!"


async def test_a_streamed_turn_becomes_part_of_the_history_for_the_next_turn():
    seen: list = []
    conversation = Conversation()
    with chat_agent.override(model=streaming_model(["Nice to meet you."], seen)):
        _ = [delta async for delta in conversation.stream("I am Priya")]
        await conversation.say("who am I?")
    assert prompts(seen[-1]) == ["I am Priya", "who am I?"]
