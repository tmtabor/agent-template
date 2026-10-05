"""Live check: the chain runs end to end and each step feeds the next. Run with `pytest -m eval`."""

import pytest

from evals.trace import traced_run
from examples.live_support import assert_every_agent_ran, run_as_script
from examples.pipeline import agent as module

pytestmark = pytest.mark.eval


async def test_the_three_steps_run_in_order_and_produce_a_piece():
    traced = await traced_run(module.run_pipeline, "Why unit tests are worth writing")

    output = traced.result.output
    assert len(output.outline) >= 3  # the outline step was asked for three to five points
    assert len(output.result.split()) >= 30  # a real piece of writing, not a stub
    assert "test" in output.result.lower()
    assert [step.agent for step in traced.result.steps] == [
        "pipeline.outline",
        "pipeline.draft",
        "pipeline.polish",
    ]
    assert traced.result.usage.requests >= 3  # one per step, plus any output retries
    assert_every_agent_ran(module, traced.agents_ran)


async def test_the_demo_script_runs():
    assert "outline=" in await run_as_script("examples.pipeline.agent")
