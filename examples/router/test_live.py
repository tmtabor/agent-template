"""Live check: each message reaches the right specialist, and every specialist runs. `-m eval`."""

import pytest

from evals.trace import traced_run
from examples.live_support import assert_every_agent_ran, run_as_script
from examples.router import agent as module

pytestmark = pytest.mark.eval

CASES = {
    "billing": "I was charged twice for my subscription this month.",
    "technical": "The app crashes with a 500 error every time I upload a file.",
    "general": "Do you have an office in Berlin?",
}


@pytest.fixture(scope="module")
async def routed():
    return {
        category: await traced_run(module.run_router, message)
        for category, message in CASES.items()
    }


@pytest.mark.parametrize("category", sorted(CASES))
async def test_a_message_is_classified_and_answered_by_its_specialist(routed, category):
    traced = routed[category]
    output = traced.result.output

    assert output.category == category
    assert output.result.strip()
    assert [step.agent for step in traced.result.steps] == [
        "router.classifier",
        f"router.{category}",
    ]
    assert traced.agents_ran == {"router.classifier", f"router.{category}"}
    assert traced.result.usage.requests >= 2  # one per step, plus any output retries


async def test_every_specialist_ran_for_real(routed):
    assert_every_agent_ran(module, set().union(*(t.agents_ran for t in routed.values())))


async def test_the_demo_script_runs():
    assert "category=" in await run_as_script("examples.router.agent")
