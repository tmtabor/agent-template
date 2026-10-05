"""Live check: the workers run in parallel and the aggregator combines them. `pytest -m eval`."""

import pytest

from evals.trace import traced_run
from examples.fan_out import agent as module
from examples.live_support import assert_every_agent_ran, run_as_script

pytestmark = pytest.mark.eval


async def test_every_perspective_is_analyzed_and_summarized():
    traced = await traced_run(module.run_fan_out, "Adopting a monorepo")

    output = traced.result.output
    assert output.perspectives_used == module.PERSPECTIVES
    assert output.perspectives_failed == []
    assert len(output.result.split()) >= 15

    labels = [step.agent for step in traced.result.steps]
    assert labels[-1] == "fan_out.aggregator"  # the aggregator runs after every worker
    assert labels[:-1] == ["fan_out.worker"] * len(module.PERSPECTIVES)
    # One request per step, plus any output retries.
    assert traced.result.usage.requests >= len(module.PERSPECTIVES) + 1
    assert_every_agent_ran(module, traced.agents_ran)


async def test_the_demo_script_runs():
    assert "perspectives_used=" in await run_as_script("examples.fan_out.agent")
