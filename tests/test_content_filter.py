"""Every agent carries RaiseContentFilterError: a content-filtered response raises.

Without the capability, pydantic_ai only raises when the filtered response is
empty — partial or refusal text would be retried (structured output) or
returned as if complete. The contrast test below pins that default.
"""

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ContentFilterError
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from tests.agent_finder import module_agents
from tests.examples_support import example_ids, import_example


def _filtered(messages, info) -> ModelResponse:
    return ModelResponse(
        parts=[TextPart("partial or refused text")],
        finish_reason="content_filter",
        provider_details={"finish_reason": "content_filter"},
    )


@pytest.mark.parametrize("example", example_ids())
async def test_every_agent_in_an_example_raises_on_content_filtered_response(example):
    """Each agent is checked directly — not just the one a flow happens to reach first."""
    module = import_example(example, running=True)
    deps = getattr(module, example.deps)()
    agents = module_agents(module)
    assert agents
    for agent in agents:
        with (
            agent.override(model=FunctionModel(_filtered)),
            pytest.raises(ContentFilterError, match="content_filter"),
        ):
            await agent.run("Smoke test input", deps=deps)


async def test_default_agent_returns_partial_text_without_the_capability():
    bare = Agent(FunctionModel(_filtered))
    result = await bare.run("hi")
    assert result.output == "partial or refused text"
