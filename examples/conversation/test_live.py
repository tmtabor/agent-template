"""Live check: the model remembers across turns, forgets what leaves the window, and streams. `-m eval`."""

import pytest

from evals.trace import traced_run
from examples.conversation import agent as module
from examples.live_support import assert_every_agent_ran, run_as_script

pytestmark = pytest.mark.eval


async def turn(conversation: module.Conversation, text: str):
    async def helper(message: str):
        return await conversation.say(message)

    return await traced_run(helper, text)


@pytest.fixture(scope="module")
async def remembering():
    conversation = module.Conversation()
    first = await turn(
        conversation, "Hi! My name is Priya and I'm planning a trip to Lisbon in May."
    )
    city = await turn(conversation, "Which city did I say I was visiting?")
    name = await turn(conversation, "And what is my name?")
    return conversation, first, city, name


@pytest.fixture(scope="module")
async def forgetting():
    """A one-turn window: by the third message, the first has left what the model can see."""
    conversation = module.Conversation(module.ChatDeps(max_turns=1))
    await turn(conversation, "My name is Priya.")
    await turn(conversation, "What is the capital of France?")
    name = await turn(conversation, "What is my name?")
    return conversation, name


@pytest.fixture(scope="module")
async def streamed():
    conversation = module.Conversation()
    chunks = [
        delta async for delta in conversation.stream("Write three short sentences about rivers.")
    ]
    follow_up = await turn(conversation, "What did I just ask you to write about?")
    return conversation, chunks, follow_up


async def test_the_model_uses_what_it_was_told_earlier(remembering):
    _, _, city, name = remembering
    assert "lisbon" in city.result.output.lower()
    assert "priya" in name.result.output.lower()


async def test_each_turn_is_one_step_and_the_history_grows(remembering):
    conversation, first, city, name = remembering
    for traced in (first, city, name):
        assert [step.agent for step in traced.result.steps] == ["conversation"]
    users = [
        p for m in conversation.history for p in m.parts if type(p).__name__ == "UserPromptPart"
    ]
    assert len(users) == 3  # nothing was dropped inside the default 20-turn window


async def test_a_turn_outside_the_window_is_really_forgotten(forgetting):
    conversation, name = forgetting
    # The model never saw "Priya" in this request, so it cannot know it. (It may say so or ask.)
    assert "priya" not in name.result.output.lower()
    users = [
        p for m in conversation.history for p in m.parts if type(p).__name__ == "UserPromptPart"
    ]
    assert "My name is Priya." not in [
        str(p.content) for p in users
    ]  # dropped from the history too


async def test_a_streamed_reply_arrives_in_pieces_that_add_up_to_what_was_said(streamed):
    conversation, chunks, _ = streamed
    assert chunks and all(isinstance(c, str) for c in chunks)
    final = conversation.history[-3]  # the streamed reply, before the follow-up turn
    assert isinstance(final.parts[0].content, str)
    assert "".join(chunks) == final.parts[0].content


async def test_a_streamed_turn_is_remembered_like_any_other(streamed):
    _, _, follow_up = streamed
    assert "river" in follow_up.result.output.lower()


async def test_the_agent_ran(remembering, forgetting, streamed):
    ran = remembering[1].agents_ran | forgetting[1].agents_ran | streamed[2].agents_ran
    assert_every_agent_ran(module, ran)


async def test_the_demo_script_runs():
    out = await run_as_script("examples.conversation.agent")
    assert "lisbon" in out.lower() and "streaming:" in out
