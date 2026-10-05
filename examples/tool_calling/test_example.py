"""The release-notes tool's three outcomes, directly and through the agent loop."""

import pytest
from pydantic_ai import ModelRetry, RunContext, ToolFailed
from pydantic_ai.messages import (
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from examples.tool_calling.agent import (
    RELEASES,
    Release,
    ToolAgentDeps,
    python_release_notes,
    run_tool_agent,
    tool_agent,
)


def ctx(deps: ToolAgentDeps | None = None) -> RunContext[ToolAgentDeps]:
    return RunContext(deps=deps or ToolAgentDeps(), model=TestModel(), usage=RunUsage())


# --- The tool, called directly ---


async def test_a_known_version_returns_its_date_and_highlights():
    notes = await python_release_notes(ctx(), "3.13")
    assert "October 7, 2024" in notes
    assert "free-threaded" in notes and "JIT" in notes


async def test_surrounding_whitespace_is_tolerated():
    assert await python_release_notes(ctx(), "  3.12 ") == await python_release_notes(ctx(), "3.12")


@pytest.mark.parametrize("version", ["latest", "3.13.1", "", "three.thirteen", "3"])
async def test_a_malformed_version_asks_the_model_to_retry(version):
    with pytest.raises(ModelRetry, match="major.minor"):
        await python_release_notes(ctx(), version)


async def test_an_unknown_version_is_a_terminal_failure_that_lists_what_exists():
    with pytest.raises(ToolFailed) as failure:
        await python_release_notes(ctx(), "3.99")
    message = str(failure.value)
    assert "3.99" in message and "3.11, 3.12, 3.13" in message and "do not guess" in message


async def test_the_backend_comes_from_deps():
    deps = ToolAgentDeps(releases={"9.9": Release("tomorrow", ("flying cars",))})
    assert "flying cars" in await python_release_notes(ctx(deps), "9.9")
    with pytest.raises(ToolFailed):
        await python_release_notes(ctx(deps), "3.13")  # not in this backend


def test_the_default_backend_is_the_shared_table():
    assert ToolAgentDeps().releases is RELEASES


# --- Through the agent loop, with a scripted model ---


def scripted(*steps: dict):
    """A model that follows `steps` in order. A step is a tool call or the final output."""
    remaining = list(steps)

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        step = remaining.pop(0)
        if "tool" in step:
            return ModelResponse(parts=[ToolCallPart(step["tool"], step["args"])])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, step["output"])])

    return FunctionModel(model_fn)


def tool_results(result) -> list[ToolReturnPart]:
    return [p for m in result.all_messages() for p in m.parts if isinstance(p, ToolReturnPart)]


async def test_the_model_calls_the_tool_and_answers_from_its_result():
    model = scripted(
        {"tool": "python_release_notes", "args": {"version": "3.13"}},
        {"output": {"result": "3.13 added a JIT.", "versions": ["3.13"]}},
    )
    with tool_agent.override(model=model):
        result = await run_tool_agent("What's new in 3.13?")

    assert result.output.versions == ["3.13"]
    tool = [r for r in tool_results(result) if r.tool_name == "python_release_notes"][0]
    assert "October 7, 2024" in tool.content and tool.outcome == "success"


async def test_a_malformed_call_is_corrected_on_retry():
    model = scripted(
        {"tool": "python_release_notes", "args": {"version": "latest"}},
        {"tool": "python_release_notes", "args": {"version": "3.13"}},
        {"output": {"result": "ok", "versions": ["3.13"]}},
    )
    with tool_agent.override(model=model):
        result = await run_tool_agent("What's the latest Python?")

    retries = [p for m in result.all_messages() for p in m.parts if isinstance(p, RetryPromptPart)]
    assert len(retries) == 1 and "major.minor" in str(retries[0].content)
    assert result.output.result == "ok"


async def test_an_unavailable_version_reaches_the_model_as_a_failure_not_a_retry():
    model = scripted(
        {"tool": "python_release_notes", "args": {"version": "3.99"}},
        {"output": {"result": "No notes exist for 3.99.", "versions": []}},
    )
    with tool_agent.override(model=model):
        result = await run_tool_agent("What's new in 3.99?")

    tool = [r for r in tool_results(result) if r.tool_name == "python_release_notes"][0]
    assert tool.outcome == "failed" and "do not guess" in tool.content
    assert not [p for m in result.all_messages() for p in m.parts if isinstance(p, RetryPromptPart)]
    assert result.usage.requests == 2
