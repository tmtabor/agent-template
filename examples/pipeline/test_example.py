"""The chain runs in order, passes each step's output on, and stops at a failed gate."""

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import UsageLimits

from examples.pipeline import agent as pipeline
from examples.pipeline.agent import (
    EmptyOutlineError,
    draft_agent,
    outline_agent,
    polish_agent,
    run_pipeline,
)


def prompt_of(messages) -> str:
    return "\n".join(str(p.content) for p in messages[-1].parts if isinstance(p, UserPromptPart))


def returns(fields: dict, seen: list[str] | None = None):
    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(prompt_of(messages))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, fields)])

    return FunctionModel(model_fn)


async def test_each_step_receives_the_previous_steps_output():
    draft_in: list[str] = []
    polish_in: list[str] = []
    with (
        outline_agent.override(model=returns({"points": ["first point", "second point"]})),
        draft_agent.override(model=returns({"text": "a rough draft"}, draft_in)),
        polish_agent.override(model=returns({"result": "a polished piece"}, polish_in)),
    ):
        result = await run_pipeline("testing")
        output = result.output

    assert output.result == "a polished piece"
    assert [step.agent for step in result.steps] == [
        "pipeline.outline",
        "pipeline.draft",
        "pipeline.polish",
    ]
    assert result.usage.requests == 3
    assert output.outline == ["first point", "second point"]
    assert "1. first point" in draft_in[0] and "2. second point" in draft_in[0]
    assert "a rough draft" in polish_in[0]


async def test_an_empty_outline_stops_the_chain_before_later_steps_run():
    def must_not_run(messages, info):
        raise AssertionError("a step after the failed gate ran")

    with (
        outline_agent.override(model=returns({"points": []})),
        draft_agent.override(model=FunctionModel(must_not_run)),
        polish_agent.override(model=FunctionModel(must_not_run)),
        pytest.raises(EmptyOutlineError),
    ):
        await run_pipeline("testing")


async def test_one_budget_covers_every_step(monkeypatch):
    """Three steps need three requests; request_limit=2 stops the chain at the third."""
    monkeypatch.setattr(pipeline, "USAGE_LIMITS", UsageLimits(request_limit=2))
    with (
        outline_agent.override(model=returns({"points": ["a"]})),
        draft_agent.override(model=returns({"text": "d"})),
        polish_agent.override(model=returns({"result": "p"})),
        pytest.raises(UsageLimitExceeded),
    ):
        await run_pipeline("testing")
