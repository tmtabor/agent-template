"""The output validator sends bad answers back to the model, within a retry budget."""

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from examples.extraction.agent import ExtractionDeps, extraction_agent, run_extraction


def answers(*contacts: dict):
    """A FunctionModel that returns each contact in turn and records what it was sent."""
    seen: list[list] = []
    remaining = list(contacts)

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        seen.append(messages)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, remaining.pop(0))])

    return FunctionModel(model_fn), seen


async def test_a_valid_contact_is_returned_as_is():
    model, seen = answers({"name": "Ada", "email": "ada@example.com"})
    with extraction_agent.override(model=model):
        result = await run_extraction("Ada, ada@example.com")
        contact = result.output
    assert contact.email == "ada@example.com"
    assert len(seen) == 1


async def test_a_bad_email_is_sent_back_for_correction():
    model, seen = answers(
        {"name": "Ada", "email": "ada at example dot com"},
        {"name": "Ada", "email": "ada@example.com"},
    )
    with extraction_agent.override(model=model):
        result = await run_extraction("Ada, ada@example.com")
        contact = result.output

    assert contact.email == "ada@example.com"
    assert len(seen) == 2
    # One agent step, and the retry is visible in its usage: two model requests.
    assert [step.agent for step in result.steps] == ["extraction"]
    assert result.usage.requests == 2
    retries = [p for p in seen[1][-1].parts if isinstance(p, RetryPromptPart)]
    assert "is not an email address" in str(retries[0].content)


async def test_a_contact_with_no_way_to_reach_them_is_rejected():
    model, _ = answers({"name": "Ada"}, {"name": "Ada", "phone": "+44 20 7946 0958"})
    with extraction_agent.override(model=model):
        result = await run_extraction("Ada, 020 7946 0958")
        contact = result.output
    assert contact.phone == "+44 20 7946 0958"


async def test_the_retry_budget_runs_out_instead_of_returning_something_invalid():
    bad = {"name": "Ada", "email": "nope"}
    model, seen = answers(bad, bad, bad)
    with extraction_agent.override(model=model), pytest.raises(UnexpectedModelBehavior):
        await extraction_agent.run("x", deps=ExtractionDeps())
    assert len(seen) == 3  # the first attempt plus retries={"output": 2}
