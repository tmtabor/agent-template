"""traced_run reports every agent and tool the spans saw — including workers inside tools."""

import pytest

from evals.trace import traced_run
from examples.router.agent import run_router
from examples.supervisor.agent import run_supervisor
from tests.examples_support import EXAMPLES, import_example, smoke_overrides


def example(name: str):
    return next(e for e in EXAMPLES if e.name == name)


async def test_a_flows_agents_are_all_reported():
    traced = await traced_run(run_router, "I was charged twice")
    assert traced.agents_ran == {"router.classifier", "router.billing"}
    assert traced.tools_called == []
    assert len(traced.result.steps) == 2


async def test_workers_inside_tool_calls_are_seen_even_though_they_are_in_no_step():
    ex = example("supervisor")
    with smoke_overrides(ex, import_example(ex)):
        traced = await traced_run(run_supervisor, "Research X, then write Y")

    assert [step.agent for step in traced.result.steps] == ["supervisor"]  # one recorded step…
    assert traced.agents_ran == {  # …but all three agents ran
        "supervisor",
        "supervisor.analyst",
        "supervisor.writer",
    }
    assert traced.tools_called == ["delegate_to_analyst", "delegate_to_writer"]


async def test_the_runs_exception_propagates():
    async def broken(text: str):
        raise RuntimeError("provider is down")

    with pytest.raises(RuntimeError, match="provider is down"):
        await traced_run(broken, "x")
