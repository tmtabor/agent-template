"""The calendar tools, the MCP server they live on, and the agent that uses them over MCP — offline.

Needs `fastmcp-slim[server]` (declared in example.toml), so it is skipped in an environment without
it and run in the example's own environment by scripts/release_check.py.
"""

import pytest

try:
    # The server half of fastmcp. Pydantic AI's MCP client installs only the client half, so
    # importing `fastmcp` alone is not enough to tell whether this example can run.
    from fastmcp import FastMCP  # noqa: F401
except ImportError:
    pytest.skip("needs fastmcp-slim[server]", allow_module_level=True)

from fastmcp import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402

from examples.mcp_tools.agent import (  # noqa: E402
    add_days,
    days_between,
    mcp_agent,
    parse_date,
    run_mcp,
    server,
    weekday,
)

# --- The tools, called directly (the @server.tool decorator leaves them ordinary functions) ---


def test_days_between_counts_across_a_leap_february():
    assert days_between("2024-02-10", "2024-03-01") == 20  # 2024 has a Feb 29
    assert days_between("2023-02-10", "2023-03-01") == 19


def test_days_between_is_zero_for_the_same_day_and_negative_going_backwards():
    assert days_between("2025-01-15", "2025-01-15") == 0
    assert days_between("2025-03-01", "2025-01-15") == -45


def test_add_days_crosses_month_boundaries_and_can_go_backwards():
    assert add_days("2025-01-15", 45) == "2025-03-01"
    assert add_days("2025-03-01", -45) == "2025-01-15"
    assert add_days("2025-12-31", 1) == "2026-01-01"


def test_weekday_names_the_day():
    assert weekday("2024-12-25") == "Wednesday"
    assert weekday("2000-01-01") == "Saturday"


def test_surrounding_whitespace_is_tolerated():
    assert parse_date(" 2025-03-01 ").isoformat() == "2025-03-01"


@pytest.mark.parametrize("bad", ["next tuesday", "2025-13-01", "2025-02-30", "", "03/01/2025"])
def test_a_malformed_date_raises_an_error_that_says_how_to_fix_it(bad):
    with pytest.raises(ValueError, match=r"Use the form YYYY-MM-DD"):
        parse_date(bad)


# --- The server, over real MCP (in memory) ---


async def test_the_server_advertises_exactly_these_tools_with_descriptions():
    async with Client(server) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    assert set(tools) == {"days_between", "add_days", "weekday"}
    assert all(
        tool.description for tool in tools.values()
    )  # the model chooses tools by description


async def test_a_tool_call_over_mcp_returns_the_result():
    async with Client(server) as client:
        result = await client.call_tool(
            "days_between", {"start": "2024-02-10", "end": "2024-03-01"}
        )
    assert result.data == 20


async def test_a_bad_argument_comes_back_over_mcp_as_an_error_naming_the_fix():
    async with Client(server) as client:
        with pytest.raises(ToolError, match="YYYY-MM-DD"):
            await client.call_tool("weekday", {"day": "next tuesday"})


# --- The agent, using the server, with a scripted model ---


def scripted(*steps: dict):
    """Follow `steps`: a tool call ({"tool", "args"}) or the final output ({"output"})."""
    remaining = list(steps)

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        step = remaining.pop(0)
        if "tool" in step:
            return ModelResponse(parts=[ToolCallPart(step["tool"], step["args"])])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, step["output"])])

    return FunctionModel(model_fn)


def tool_returns(result) -> list[ToolReturnPart]:
    return [
        p
        for m in result.all_messages()
        for p in m.parts
        if isinstance(p, ToolReturnPart) and p.tool_name != "final_result"
    ]


def retries(result) -> list[RetryPromptPart]:
    return [p for m in result.all_messages() for p in m.parts if isinstance(p, RetryPromptPart)]


async def test_the_model_sees_the_servers_tools_and_calls_one_over_mcp():
    seen_tools: list[str] = []

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        if not seen_tools:
            seen_tools.extend(tool.name for tool in info.function_tools)
            args = {"start": "2024-02-10", "end": "2024-03-01"}
            return ModelResponse(parts=[ToolCallPart("days_between", args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"result": "20 days"})])

    with mcp_agent.override(model=FunctionModel(model_fn)):
        result = await run_mcp("How many days from 2024-02-10 to 2024-03-01?")

    assert set(seen_tools) == {"days_between", "add_days", "weekday"}  # discovered, not hard-coded
    assert [str(r.content) for r in tool_returns(result)] == ["20"]  # computed by the server
    assert result.output.result == "20 days"
    assert [step.agent for step in result.steps] == ["mcp_tools"]


async def test_a_server_error_is_shown_to_the_model_which_then_corrects_its_call():
    model = scripted(
        {"tool": "weekday", "args": {"day": "next tuesday"}},
        {"tool": "weekday", "args": {"day": "2025-03-04"}},
        {"output": {"result": "Tuesday"}},
    )
    with mcp_agent.override(model=model):
        result = await run_mcp("What weekday is next tuesday?")

    assert len(retries(result)) == 1 and "YYYY-MM-DD" in str(retries(result)[0].content)
    assert [str(r.content) for r in tool_returns(result)] == ["Tuesday"]
    assert result.output.result == "Tuesday"


async def test_several_tools_can_be_used_in_one_run():
    model = scripted(
        {"tool": "add_days", "args": {"start": "2025-01-15", "days": 45}},
        {"tool": "weekday", "args": {"day": "2025-03-01"}},
        {"output": {"result": "2025-03-01 is a Saturday"}},
    )
    with mcp_agent.override(model=model):
        result = await run_mcp("What is 45 days after 2025-01-15, and what weekday?")
    assert [str(r.content) for r in tool_returns(result)] == ["2025-03-01", "Saturday"]
