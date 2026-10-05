"""Live check: the blank agent runs against the real model. Run with `pytest -m eval`."""

import pytest

from evals.trace import traced_run
from examples.blank import agent as module
from examples.live_support import assert_every_agent_ran, run_as_script

pytestmark = pytest.mark.eval


async def test_the_agent_answers():
    traced = await traced_run(module.run_blank_agent, "Hello, what can you do?")

    assert isinstance(traced.result.output, module.BlankOutput)
    assert traced.result.output.result.strip()
    assert [step.agent for step in traced.result.steps] == ["blank"]
    assert traced.result.usage.requests >= 1  # more if the model retried its output
    assert_every_agent_ran(module, traced.agents_ran)


async def test_the_demo_script_runs():
    assert "result=" in await run_as_script("examples.blank.agent")
