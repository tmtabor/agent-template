"""Live check: the single agent runs against the real model. Run with `pytest -m eval`."""

import pytest

from evals.trace import traced_run
from examples.live_support import assert_every_agent_ran, run_as_script
from examples.single import agent as module

pytestmark = pytest.mark.eval


async def test_the_agent_answers_with_a_valid_confidence():
    traced = await traced_run(module.run_agent, "Explain what an AI agent is in one sentence.")

    output = traced.result.output
    assert isinstance(output, module.AgentOutput)
    assert "agent" in output.result.lower()
    assert 0.0 <= output.confidence <= 1.0
    assert [step.agent for step in traced.result.steps] == ["single"]
    assert traced.result.usage.requests >= 1  # more if the model retried its output
    assert_every_agent_ran(module, traced.agents_ran)


async def test_the_demo_script_runs():
    assert "result=" in await run_as_script("examples.single.agent")
