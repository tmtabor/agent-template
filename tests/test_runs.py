"""RunResult and Flow: uniform results with one shared budget."""

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits

from agent.runs import Flow, RunResult


def make(name: str | None = "one") -> Agent:
    return Agent(TestModel(custom_output_text="hello"), name=name)


async def test_a_flow_records_each_step_in_order():
    first, second = make("first"), make("second")
    flow = Flow(UsageLimits())
    await flow.run(first, "a", deps=None)
    await flow.run(second, "b", deps=None)
    result = flow.finish("done")

    assert isinstance(result, RunResult)
    assert result.output == "done"
    assert [step.agent for step in result.steps] == ["first", "second"]


async def test_steps_hold_the_native_results():
    flow = Flow(UsageLimits())
    native = await flow.run(make(), "a", deps=None)
    result = flow.finish(native.output)
    assert result.steps[0].result is native
    assert result.output == "hello"


async def test_usage_is_the_shared_total_not_a_double_count():
    flow = Flow(UsageLimits())
    for _ in range(3):
        await flow.run(make(), "a", deps=None)
    result = flow.finish("done")
    assert result.usage.requests == 3  # three steps, one request each, counted once


async def test_the_limits_bound_the_whole_flow_not_each_step():
    flow = Flow(UsageLimits(request_limit=2))
    await flow.run(make(), "a", deps=None)
    await flow.run(make(), "b", deps=None)
    with pytest.raises(UsageLimitExceeded):
        await flow.run(make(), "c", deps=None)


async def test_a_failed_step_is_not_recorded():
    flow = Flow(UsageLimits(request_limit=1))
    await flow.run(make(), "a", deps=None)
    with pytest.raises(UsageLimitExceeded):
        await flow.run(make(), "b", deps=None)
    assert len(flow.finish("x").steps) == 1


async def test_all_messages_spans_every_step():
    flow = Flow(UsageLimits())
    first = await flow.run(make(), "a", deps=None)
    second = await flow.run(make(), "b", deps=None)
    result = flow.finish("x")
    assert len(result.all_messages()) == len(first.all_messages()) + len(second.all_messages())


async def test_an_unnamed_agent_gets_a_default_label():
    flow = Flow(UsageLimits())
    await flow.run(make(name=None), "a", deps=None)
    assert flow.finish("x").steps[0].agent == "agent"
