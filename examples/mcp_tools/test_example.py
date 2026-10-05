"""The calendar server, the agent that uses it over HTTP, and what happens when it is down — offline.

The tests that need the server half of fastmcp (`test_dependencies` in example.toml) run it as a
local subprocess (see conftest.py) and are skipped without it; the release check runs them in the
example's own environment.
"""

import importlib.util
import runpy
from pathlib import Path

import pytest
from pydantic_ai.messages import (
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from examples.mcp_tools import agent as module
from examples.mcp_tools.agent import (
    DEFAULT_SERVER_URL,
    McpDeps,
    McpServerUnavailable,
    mcp_agent,
    run_mcp,
    server_url_from_env,
)

SERVER_PATH = Path(__file__).parent / "service" / "server.py"


@pytest.fixture(scope="module")
def calendar():
    """The server module, loaded by path (it is a standalone service, not part of the package)."""
    try:
        spec = importlib.util.spec_from_file_location("calendar_server", SERVER_PATH)
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
    except ImportError:
        pytest.skip("needs fastmcp-slim[server]")
    return loaded


# --- The server's tools, called directly (the @server.tool decorator leaves them ordinary functions) ---


def test_days_between_counts_across_a_leap_february(calendar):
    assert calendar.days_between("2024-02-10", "2024-03-01") == 20  # 2024 has a Feb 29
    assert calendar.days_between("2023-02-10", "2023-03-01") == 19


def test_days_between_is_zero_for_the_same_day_and_negative_going_backwards(calendar):
    assert calendar.days_between("2025-01-15", "2025-01-15") == 0
    assert calendar.days_between("2025-03-01", "2025-01-15") == -45


def test_add_days_crosses_month_boundaries_and_can_go_backwards(calendar):
    assert calendar.add_days("2025-01-15", 45) == "2025-03-01"
    assert calendar.add_days("2025-03-01", -45) == "2025-01-15"
    assert calendar.add_days("2025-12-31", 1) == "2026-01-01"


def test_weekday_names_the_day(calendar):
    assert calendar.weekday("2024-12-25") == "Wednesday"
    assert calendar.weekday("2000-01-01") == "Saturday"


def test_surrounding_whitespace_is_tolerated(calendar):
    assert calendar.parse_date(" 2025-03-01 ").isoformat() == "2025-03-01"


@pytest.mark.parametrize("bad", ["next tuesday", "2025-13-01", "2025-02-30", "", "03/01/2025"])
def test_a_malformed_date_raises_an_error_that_says_how_to_fix_it(calendar, bad):
    with pytest.raises(ValueError, match=r"Use the form YYYY-MM-DD"):
        calendar.parse_date(bad)


# --- Serving ---


def test_main_serves_over_http_on_the_configured_address(calendar, monkeypatch):
    served = {}
    monkeypatch.setattr(
        calendar.server, "run", lambda **kwargs: served.update(kwargs), raising=False
    )
    monkeypatch.setenv(
        "MCP_HOST", "0.0.0.0"
    )  # what the container sets, so the port can be published
    monkeypatch.setenv("MCP_PORT", "9123")
    calendar.main()
    assert served == {"transport": "http", "host": "0.0.0.0", "port": 9123}


def test_main_defaults_to_localhost_port_8000(calendar, monkeypatch):
    served = {}
    monkeypatch.setattr(
        calendar.server, "run", lambda **kwargs: served.update(kwargs), raising=False
    )
    monkeypatch.delenv("MCP_HOST", raising=False)
    monkeypatch.delenv("MCP_PORT", raising=False)
    calendar.main()
    assert served == {"transport": "http", "host": "127.0.0.1", "port": 8000}


def test_running_the_file_as_a_script_starts_the_server(calendar, monkeypatch):
    import fastmcp

    started = []
    monkeypatch.setattr(fastmcp.FastMCP, "run", lambda self, **kwargs: started.append(kwargs))
    runpy.run_path(str(SERVER_PATH), run_name="__main__")
    assert started and started[0]["transport"] == "http"


# --- The server, over real MCP and a real network connection ---


async def test_the_server_advertises_exactly_these_tools_with_descriptions(server_url):
    from fastmcp import Client

    async with Client(server_url) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    assert set(tools) == {"days_between", "add_days", "weekday"}
    assert all(
        tool.description for tool in tools.values()
    )  # the model chooses tools by description


async def test_a_tool_call_over_the_network_returns_the_result(server_url):
    from fastmcp import Client

    async with Client(server_url) as client:
        result = await client.call_tool(
            "days_between", {"start": "2024-02-10", "end": "2024-03-01"}
        )
    assert result.data == 20


async def test_a_bad_argument_comes_back_over_the_network_as_an_error_naming_the_fix(server_url):
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    async with Client(server_url) as client:
        with pytest.raises(ToolError, match="YYYY-MM-DD"):
            await client.call_tool("weekday", {"day": "next tuesday"})


# --- The agent, using the server over HTTP, with a scripted model ---


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


async def test_the_model_sees_the_servers_tools_and_calls_one_over_the_network(server_url):
    seen_tools: list[str] = []

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        if not seen_tools:
            seen_tools.extend(tool.name for tool in info.function_tools)
            args = {"start": "2024-02-10", "end": "2024-03-01"}
            return ModelResponse(parts=[ToolCallPart("days_between", args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"result": "20 days"})])

    with mcp_agent.override(model=FunctionModel(model_fn)):
        result = await run_mcp("How many days?", McpDeps(server_url))

    assert set(seen_tools) == {"days_between", "add_days", "weekday"}  # discovered, not hard-coded
    assert [str(r.content) for r in tool_returns(result)] == ["20"]  # computed by the service
    assert result.output.result == "20 days"
    assert [step.agent for step in result.steps] == ["mcp_tools"]


async def test_a_server_error_is_shown_to_the_model_which_then_corrects_its_call(server_url):
    model = scripted(
        {"tool": "weekday", "args": {"day": "next tuesday"}},
        {"tool": "weekday", "args": {"day": "2025-03-04"}},
        {"output": {"result": "Tuesday"}},
    )
    with mcp_agent.override(model=model):
        result = await run_mcp("What weekday is next tuesday?", McpDeps(server_url))

    assert len(retries(result)) == 1 and "YYYY-MM-DD" in str(retries(result)[0].content)
    assert [str(r.content) for r in tool_returns(result)] == ["Tuesday"]


async def test_several_tools_can_be_used_in_one_run(server_url):
    model = scripted(
        {"tool": "add_days", "args": {"start": "2025-01-15", "days": 45}},
        {"tool": "weekday", "args": {"day": "2025-03-01"}},
        {"output": {"result": "2025-03-01 is a Saturday"}},
    )
    with mcp_agent.override(model=model):
        result = await run_mcp("45 days after 2025-01-15, and the weekday?", McpDeps(server_url))
    assert [str(r.content) for r in tool_returns(result)] == ["2025-03-01", "Saturday"]


# --- The address comes from deps ---


def test_the_server_address_defaults_to_the_local_service(monkeypatch):
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    assert server_url_from_env() == DEFAULT_SERVER_URL == "http://127.0.0.1:8000/mcp"
    assert McpDeps().server_url == DEFAULT_SERVER_URL


def test_the_server_address_can_be_set_in_the_environment(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "http://staging.internal:9000/mcp")
    assert McpDeps().server_url == "http://staging.internal:9000/mcp"
    assert McpDeps("http://elsewhere/mcp").server_url == "http://elsewhere/mcp"  # deps win


# --- When the server is not there ---


async def test_an_unreachable_server_is_reported_with_where_it_looked_and_how_to_start_it():
    dead = McpDeps("http://127.0.0.1:1/mcp")  # nothing listens on port 1
    with (
        mcp_agent.override(model=scripted({"output": {"result": "never"}})),
        pytest.raises(McpServerUnavailable) as failure,
    ):
        await run_mcp("How many days?", dead)
    message = str(failure.value)
    assert "http://127.0.0.1:1/mcp" in message and "docker compose" in message
    assert isinstance(failure.value.__cause__, RuntimeError)  # the original error is kept


async def test_other_runtime_errors_are_not_mistaken_for_a_missing_server(monkeypatch):
    def broken(url: str):
        raise RuntimeError("the tool schema was invalid")

    monkeypatch.setattr(module, "MCPToolset", broken)
    with (
        mcp_agent.override(model=scripted({"output": {"result": "never"}})),
        pytest.raises(RuntimeError, match="tool schema was invalid") as failure,
    ):
        await run_mcp("How many days?", McpDeps("http://127.0.0.1:1/mcp"))
    assert not isinstance(failure.value, McpServerUnavailable)  # passed through unchanged
