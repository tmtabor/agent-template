"""Routing is a dictionary lookup: each category reaches its own specialist."""

import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import UsageLimits

from examples.router import agent as router
from examples.router.agent import (
    SPECIALISTS,
    Classification,
    router_agent,
    run_router,
)


def returns(**fields):
    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, fields)])

    return FunctionModel(model_fn)


@pytest.mark.parametrize("category", sorted(SPECIALISTS))
async def test_each_category_reaches_its_own_specialist(category):
    # Every specialist answers with its own name, so a misroute shows in the result.
    overrides = [SPECIALISTS[c].override(model=returns(result=f"{c} answer")) for c in SPECIALISTS]
    with router_agent.override(model=returns(category=category)):
        for override in overrides:
            override.__enter__()
        try:
            result = await run_router("anything")
            output = result.output
        finally:
            for override in reversed(overrides):
                override.__exit__(None, None, None)

    assert output.category == category
    assert output.result == f"{category} answer"
    # The result records the route taken: the classifier, then that category's specialist.
    assert [step.agent for step in result.steps] == ["router.classifier", f"router.{category}"]
    assert result.usage.requests == 2


def test_the_classifier_can_only_return_a_known_category():
    with pytest.raises(ValidationError):
        Classification(category="astrology")


async def test_one_budget_covers_the_classifier_and_the_specialist(monkeypatch):
    """USAGE_LIMITS bounds the whole route: two requests exceed request_limit=1."""
    monkeypatch.setattr(router, "USAGE_LIMITS", UsageLimits(request_limit=1))
    with (
        router_agent.override(model=returns(category="general")),
        SPECIALISTS["general"].override(model=returns(result="hi")),
        pytest.raises(UsageLimitExceeded),
    ):
        await run_router("hello")
