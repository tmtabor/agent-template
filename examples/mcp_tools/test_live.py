"""Live check: the model uses the MCP server's tools for exact answers, over real MCP. `-m eval`.

Needs `fastmcp-slim[server]` (declared in example.toml); run by scripts/release_check.py in the
example's own environment.
"""

import pytest

try:
    # The server half of fastmcp. Pydantic AI's MCP client installs only the client half, so
    # importing `fastmcp` alone is not enough to tell whether this example can run.
    from fastmcp import FastMCP  # noqa: F401
except ImportError:
    pytest.skip("needs fastmcp-slim[server]", allow_module_level=True)

from evals.trace import traced_run  # noqa: E402
from examples.live_support import assert_every_agent_ran, run_as_script  # noqa: E402
from examples.mcp_tools import agent as module  # noqa: E402

pytestmark = pytest.mark.eval


@pytest.fixture(scope="module")
async def leap_days():
    return await traced_run(
        module.run_mcp, "How many days are there from 2024-02-10 to 2024-03-01?"
    )


@pytest.fixture(scope="module")
async def forward():
    return await traced_run(module.run_mcp, "What date is 45 days after 2025-01-15?")


@pytest.fixture(scope="module")
async def day_name():
    return await traced_run(module.run_mcp, "What day of the week is 2024-12-25?")


async def test_a_calendar_question_is_answered_with_the_servers_exact_result(leap_days):
    assert "days_between" in leap_days.tools_called  # it used the tool rather than counting itself
    assert (
        "20" in leap_days.result.output.result
    )  # 2024 is a leap year: 19 would be the naive answer


async def test_date_arithmetic_comes_from_the_tool(forward):
    assert "add_days" in forward.tools_called
    assert "2025-03-01" in forward.result.output.result


async def test_a_weekday_question_uses_the_weekday_tool(day_name):
    assert "weekday" in day_name.tools_called
    assert "wednesday" in day_name.result.output.result.lower()


async def test_the_tool_results_in_the_history_are_the_servers_not_the_models(
    leap_days, forward, day_name
):
    """The tool-return parts come from the MCP server; the answers must agree with them."""
    for traced, expected in ((leap_days, "20"), (forward, "2025-03-01"), (day_name, "Wednesday")):
        returns = [
            str(part.content)
            for message in traced.result.all_messages()
            for part in message.parts
            if type(part).__name__ == "ToolReturnPart" and part.tool_name != "final_result"
        ]
        assert expected in returns


async def test_the_agent_ran(leap_days, forward, day_name):
    assert_every_agent_ran(module, leap_days.agents_ran | forward.agents_ran | day_name.agents_ran)


async def test_the_demo_script_runs():
    out = await run_as_script("examples.mcp_tools.agent")
    assert "result=" in out
