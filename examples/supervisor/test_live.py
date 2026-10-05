"""Live check: the supervisor delegates to real workers and synthesizes. Run with `pytest -m eval`."""

import pytest

from evals.trace import traced_run
from examples.live_support import assert_every_agent_ran, run_as_script
from examples.supervisor import agent as module

pytestmark = pytest.mark.eval


@pytest.fixture(scope="module")
async def research_and_write():
    return await traced_run(
        module.run_supervisor,
        "Research the pros and cons of remote work, then write two sentences about it for a manager.",
    )


@pytest.fixture(scope="module")
async def write_only():
    return await traced_run(module.run_supervisor, "Say hello in French.")


async def test_a_research_and_write_request_uses_both_workers_in_order(research_and_write):
    traced = research_and_write
    assert traced.tools_called == ["delegate_to_analyst", "delegate_to_writer"]
    assert traced.agents_ran == {"supervisor", "supervisor.analyst", "supervisor.writer"}

    output = traced.result.output
    assert len(output.result.split()) >= 10
    # steps_taken is the model's own account; it should name both workers, analyst first.
    named = [s.lower() for s in output.steps_taken]
    assert any("analyst" in s for s in named) and any("writer" in s for s in named)
    assert min(i for i, s in enumerate(named) if "analyst" in s) < max(
        i for i, s in enumerate(named) if "writer" in s
    )
    # The workers' requests count against the one shared budget.
    assert traced.result.usage.requests >= 5
    assert [step.agent for step in traced.result.steps] == ["supervisor"]


async def test_a_simple_request_is_answered_without_needing_every_worker(write_only):
    # Whether the model uses the writer or answers directly is its call; either way, it answers.
    assert any(w in write_only.result.output.result.lower() for w in ("bonjour", "salut"))


async def test_every_agent_ran(research_and_write, write_only):
    assert_every_agent_ran(module, research_and_write.agents_ran | write_only.agents_ran)


async def test_the_demo_script_runs():
    assert "result=" in await run_as_script("examples.supervisor.agent")
