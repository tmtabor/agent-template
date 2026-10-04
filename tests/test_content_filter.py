"""Every agent carries RaiseContentFilterError: a content-filtered response raises.

Without the capability, pydantic_ai only raises when the filtered response is
empty — partial or refusal text would be retried (structured output) or
returned as if complete. The contrast test below pins that default.
"""

import importlib

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ContentFilterError
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from tests.test_stubs import STUBS


def _filtered(messages, info) -> ModelResponse:
    return ModelResponse(
        parts=[TextPart("partial or refused text")],
        finish_reason="content_filter",
        provider_details={"finish_reason": "content_filter"},
    )


@pytest.mark.parametrize(("module_path", "agent_attr", "deps_attr"), STUBS)
async def test_stub_raises_on_content_filtered_response(
    module_path: str, agent_attr: str, deps_attr: str
):
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        pytest.skip(f"{module_path} stub was removed by choose_pattern.py")

    main_agent = getattr(module, agent_attr)
    deps = getattr(module, deps_attr)()
    with (
        main_agent.override(model=FunctionModel(_filtered)),
        pytest.raises(ContentFilterError, match="content_filter"),
    ):
        await main_agent.run("Smoke test input", deps=deps)


async def test_default_agent_returns_partial_text_without_the_capability():
    bare = Agent(FunctionModel(_filtered))
    result = await bare.run("hi")
    assert result.output == "partial or refused text"
