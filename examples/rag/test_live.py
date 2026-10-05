"""Live check: the model searches, answers from the documents, and cites only what it found. `-m eval`."""

import pytest

from evals.trace import traced_run
from examples.live_support import assert_every_agent_ran, run_as_script
from examples.rag import agent as module

pytestmark = pytest.mark.eval


@pytest.fixture(scope="module")
async def returns():
    return await traced_run(module.run_rag, "How many days do I have to return a pair of boots?")


@pytest.fixture(scope="module")
async def two_topics():
    return await traced_run(
        module.run_rag, "Is shipping free on a $60 order, and how long is the boot warranty?"
    )


@pytest.fixture(scope="module")
async def not_covered():
    return await traced_run(module.run_rag, "Do you sell tents?")


async def test_a_question_is_answered_from_the_documents_with_its_source(returns):
    # "45 days" exists only in the invented policy, so it can't come from the model's memory.
    assert "search_docs" in returns.tools_called
    output = returns.result.output
    assert "45" in output.result
    assert "returns-policy" in output.sources


async def test_a_two_part_question_draws_on_both_passages(two_topics):
    output = two_topics.result.output
    assert {"shipping-rates", "warranty-boots"} <= set(output.sources)
    answer = output.result.lower()
    assert "75" in answer  # free shipping starts above $75, so $60 pays the standard rate
    assert "3" in answer and "year" in answer  # the 3-year boot warranty


async def test_every_citation_is_a_passage_the_model_really_retrieved(returns, two_topics):
    """The output validator enforces this; the message history shows the same thing independently."""
    for traced in (returns, two_topics):
        seen = " ".join(
            str(part.content)
            for message in traced.result.all_messages()
            for part in message.parts
            if type(part).__name__ == "ToolReturnPart" and part.tool_name == "search_docs"
        )
        for source in traced.result.output.sources:
            assert f"[{source}]" in seen


async def test_a_question_the_documents_do_not_cover_cites_nothing(not_covered):
    assert "search_docs" in not_covered.tools_called  # it looked
    assert not_covered.result.output.sources == []
    assert not_covered.result.output.result.strip()  # and it said something rather than nothing


async def test_the_agent_ran(returns, two_topics, not_covered):
    ran = returns.agents_ran | two_topics.agents_ran | not_covered.agents_ran
    assert_every_agent_ran(module, ran)


async def test_the_demo_script_runs():
    assert "returns-policy" in await run_as_script("examples.rag.agent")
