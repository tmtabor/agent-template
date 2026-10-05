"""Live check: the model uses the tool, answers from it, and handles a failure. `pytest -m eval`."""

import re

import pytest
from pydantic_ai.messages import ToolReturnPart

from evals.trace import traced_run
from examples.live_support import assert_every_agent_ran, run_as_script
from examples.tool_calling import agent as module

pytestmark = pytest.mark.eval

# Everything the table says about the versions it does know. An answer about a version it has no
# notes for must contain none of it (that would be borrowing another release's facts).
KNOWN_FACTS = {r.released.lower() for r in module.RELEASES.values()} | {
    pep.lower()
    for r in module.RELEASES.values()
    for highlight in r.highlights
    for pep in re.findall(r"PEP \d+", highlight)
}


def tool_returns(traced) -> list[ToolReturnPart]:
    return [
        p
        for m in traced.result.all_messages()
        for p in m.parts
        if isinstance(p, ToolReturnPart) and p.tool_name == "python_release_notes"
    ]


@pytest.fixture(scope="module")
async def known():
    return await traced_run(
        module.run_tool_agent, "What changed in Python 3.13 compared with 3.12?"
    )


@pytest.fixture(scope="module")
async def unknown():
    return await traced_run(module.run_tool_agent, "What's new in Python 3.99?")


async def test_a_known_version_is_answered_from_the_tool(known):
    assert known.tools_called and set(known.tools_called) == {"python_release_notes"}
    assert {r.outcome for r in tool_returns(known)} == {"success"}

    answer = known.result.output.result.lower()
    assert "october 7, 2024" in answer or "free-threaded" in answer or "jit" in answer
    assert "3.13" in known.result.output.versions
    assert known.result.usage.requests >= 2  # the tool call, then the answer
    assert_every_agent_ran(module, known.agents_ran | {"tool_calling"})


async def test_an_unknown_version_fails_the_tool_and_the_model_says_so_without_guessing(unknown):
    returns = tool_returns(unknown)
    assert returns and returns[0].outcome == "failed"  # ToolFailed, not a retry

    # However the model words it, the answer is about 3.99 and borrows nothing from the table.
    answer = unknown.result.output.result.lower()
    assert answer.strip() and "3.99" in answer
    assert not [fact for fact in KNOWN_FACTS if fact in answer], answer
    assert unknown.result.usage.requests >= 2  # the failed call, then the answer


async def test_the_demo_script_runs():
    assert "result=" in await run_as_script("examples.tool_calling.agent")
