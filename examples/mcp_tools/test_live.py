"""Live check: the model uses the tools of an MCP server running as a Docker service. `-m eval`.

The release check (scripts/release_check.py) builds and starts the service, then runs this with its
address in MCP_SERVER_URL. To run it by hand: start the service, then set the variable:

    docker compose -f examples/mcp_tools/service/docker-compose.yml up -d --wait
    export MCP_SERVER_URL=http://127.0.0.1:$(docker compose -f examples/mcp_tools/service/docker-compose.yml port mcp-server 8000 | cut -d: -f2)/mcp
"""

import os

import pytest

from evals.trace import traced_run
from examples.live_support import assert_every_agent_ran, run_as_script
from examples.mcp_tools import agent as module

pytestmark = pytest.mark.eval

if not os.environ.get("MCP_SERVER_URL"):
    pytest.skip("needs the calendar service running (MCP_SERVER_URL)", allow_module_level=True)


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


async def test_a_calendar_question_is_answered_with_the_services_exact_result(leap_days):
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


async def test_the_tool_results_in_the_history_are_the_services_not_the_models(
    leap_days, forward, day_name
):
    """The tool-return parts came back over the network from the service; the answers must agree."""
    for traced, expected in ((leap_days, "20"), (forward, "2025-03-01"), (day_name, "Wednesday")):
        returns = [
            str(part.content)
            for message in traced.result.all_messages()
            for part in message.parts
            if type(part).__name__ == "ToolReturnPart" and part.tool_name != "final_result"
        ]
        assert expected in returns


async def test_the_agent_talks_to_the_service_not_to_something_in_process(leap_days):
    """The address is the one Docker published, so the calls really crossed a network boundary."""
    assert module.McpDeps().server_url == os.environ["MCP_SERVER_URL"]
    assert module.McpDeps().server_url.startswith("http://127.0.0.1:")


async def test_the_agent_ran(leap_days, forward, day_name):
    assert_every_agent_ran(module, leap_days.agents_ran | forward.agents_ran | day_name.agents_ran)


async def test_the_demo_script_runs():
    out = await run_as_script("examples.mcp_tools.agent")
    assert "result=" in out
