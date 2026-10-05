"""Live check: the generate/critique loop's bookkeeping holds on real model output. `-m eval`.

How many rounds the real critic takes varies from run to run, so these assert the loop's
invariants for whichever path occurs rather than a particular verdict.
"""

import pytest

from evals.trace import traced_run
from examples.evaluator_optimizer import agent as module
from examples.live_support import assert_every_agent_ran, run_as_script

pytestmark = pytest.mark.eval

ITEMS = ["A stainless steel water bottle", "A wireless mechanical keyboard"]


@pytest.fixture(scope="module")
async def runs():
    return [await traced_run(module.run_evaluator_optimizer, item) for item in ITEMS]


async def test_the_loop_stops_for_a_real_reason_and_its_bookkeeping_is_consistent(runs):
    for traced in runs:
        output = traced.result.output
        steps = traced.result.steps

        assert 1 <= output.iterations <= module.MAX_ITERATIONS
        # It stopped because the critic accepted, or because it hit the cap — nothing else.
        assert output.accepted or output.iterations == module.MAX_ITERATIONS
        # One generate step and one critique step per round, alternating.
        assert [s.agent for s in steps] == [
            "evaluator_optimizer.generator",
            "evaluator_optimizer.critic",
        ] * output.iterations
        # The returned text is the last draft, and `accepted` is the last verdict.
        assert output.result == steps[-2].result.output.result
        assert output.accepted == steps[-1].result.output.accepted
        assert output.result.strip()


async def test_feedback_from_a_rejection_reaches_the_next_draft(runs):
    revised = [t for t in runs if t.result.output.iterations > 1]
    if not revised:
        pytest.skip("the real critic accepted every first draft, so no revision happened")
    steps = revised[0].result.steps
    rejection = steps[1].result.output
    assert rejection.accepted is False and rejection.feedback.strip()
    second_prompt = next(
        str(part.content)
        for message in steps[2].result.all_messages()
        for part in message.parts
        if type(part).__name__ == "UserPromptPart"
    )
    assert rejection.feedback in second_prompt and steps[0].result.output.result in second_prompt


async def test_both_agents_ran(runs):
    assert_every_agent_ran(module, set().union(*(t.agents_ran for t in runs)))


async def test_the_demo_script_runs():
    assert "iterations=" in await run_as_script("examples.evaluator_optimizer.agent")
