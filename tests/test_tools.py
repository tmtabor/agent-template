"""Unit tests for the tool error convention in agent/tools/example.py.

ModelRetry: the LLM can fix its input. ToolFailed: expected, terminal failure.
Anything unexpected propagates as a normal exception.
"""

import pytest
from pydantic_ai import Agent, ModelRetry, RunContext, ToolFailed
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from agent.tools import example


@pytest.fixture
def ctx() -> RunContext[object]:
    return RunContext(deps=object(), model=TestModel(), usage=RunUsage())


async def test_search_returns_results(ctx):
    output = await example.search_tool(ctx, "cats", max_results=2)
    assert output.splitlines() == ["Result 1 for 'cats'", "Result 2 for 'cats'"]


@pytest.mark.parametrize(("query", "max_results"), [("  ", 5), ("cats", 0), ("cats", 21)])
async def test_invalid_input_raises_model_retry(ctx, query, max_results):
    with pytest.raises(ModelRetry):
        await example.search_tool(ctx, query, max_results)


async def test_lookup_error_raises_tool_failed(ctx, monkeypatch):
    def not_found(query, max_results):
        raise LookupError("no such index")

    monkeypatch.setattr(example, "_search_backend", not_found)
    with pytest.raises(ToolFailed, match="no such index"):
        await example.search_tool(ctx, "cats")


async def test_connection_error_raises_model_retry(ctx, monkeypatch):
    def down(query, max_results):
        raise ConnectionError("refused")

    monkeypatch.setattr(example, "_search_backend", down)
    with pytest.raises(ModelRetry):
        await example.search_tool(ctx, "cats")


async def test_unexpected_error_propagates(ctx, monkeypatch):
    def broken(query, max_results):
        raise RuntimeError("bug")

    monkeypatch.setattr(example, "_search_backend", broken)
    with pytest.raises(RuntimeError, match="bug"):
        await example.search_tool(ctx, "cats")


async def test_tool_failed_reaches_model_without_spending_retries():
    """The model sees a failed tool return and answers; retries=0 proves no budget is used."""

    def model_fn(messages, info):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("lookup", {})])
        return ModelResponse(parts=[TextPart("unavailable")])

    test_agent = Agent(FunctionModel(model_fn))

    @test_agent.tool_plain(retries=0)
    def lookup() -> str:
        raise ToolFailed("not found")

    result = await test_agent.run("find it")
    returns = [p for m in result.all_messages() for p in m.parts if isinstance(p, ToolReturnPart)]
    assert result.output == "unavailable"
    assert [r.outcome for r in returns] == ["failed"]
