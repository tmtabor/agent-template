"""Live check: a real model runs as a durable Temporal workflow against the real server. `-m eval`.

The release check (scripts/release_check.py) builds and starts the Temporal service, then runs this
with its address in TEMPORAL_ADDRESS. To run it by hand: start the service, then set the variable:

    docker compose -f examples/temporal/service/docker-compose.yml up -d --wait
    export TEMPORAL_ADDRESS=$(docker compose -f examples/temporal/service/docker-compose.yml port temporal 7233)
"""

import os
import uuid

import pytest

pytest.importorskip("temporalio", reason="needs temporalio")

from pydantic_ai.messages import RetryPromptPart, ToolCallPart, ToolReturnPart  # noqa: E402

from evals.trace import traced_run  # noqa: E402
from examples.live_support import assert_every_agent_ran, run_as_script  # noqa: E402
from examples.temporal import agent as module  # noqa: E402
from examples.temporal.agent import (  # noqa: E402
    CARRIER,
    DeskDeps,
    connect,
    quote_for,
    run_order_desk,
)
from examples.temporal.test_example import (  # noqa: E402
    activities,
    model_requests,
    tool_activity,
)

pytestmark = pytest.mark.eval

if not os.environ.get("TEMPORAL_ADDRESS"):
    pytest.skip("needs the Temporal service running (TEMPORAL_ADDRESS)", allow_module_level=True)


@pytest.fixture(autouse=True)
def flaky_carrier():
    """The carrier is down on the first try of each shipment, as it is in the demo."""
    CARRIER.reset()
    CARRIER.fail_first = 1
    yield
    CARRIER.reset()


async def ask(question: str):
    """Run one question; returns the traced run, its workflow id, and the carrier calls it made."""
    workflow_id = f"live-{uuid.uuid4()}"

    async def run(text: str):
        return await run_order_desk(text, workflow_id=workflow_id)

    traced = await traced_run(run, question)
    return traced, workflow_id


def tool_names(result) -> set[str]:
    return {
        part.tool_name
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name != "final_result"
    }


async def test_the_quote_is_right_even_though_the_carrier_failed_first():
    traced, _ = await ask(
        "I'd like to order 3 gizmos for Norway. Are they in stock, and what is the shipping?"
    )
    output = traced.result.output

    expected = quote_for("gizmo", 3, "Norway")  # 20.30, worked out independently of the model
    assert output.shipping_usd == pytest.approx(expected)
    assert f"{expected:.2f}" in output.result
    assert {"check_stock", "shipping_quote"} <= tool_names(traced.result)
    # The carrier really did fail on the first call and succeed on a later one.
    outcomes = [ok for _, ok in CARRIER.attempts]
    assert outcomes[0] is False and outcomes[-1] is True


async def test_the_model_never_saw_the_failure_and_was_never_asked_twice_for_one_answer():
    traced, workflow_id = await ask("What does it cost to ship 2 widgets to Germany?")
    result = traced.result

    assert not [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]
    by_name = await activities(await connect(DeskDeps().temporal_address), workflow_id)
    model = model_requests(by_name)
    # The server ran each model request exactly once, and as many as the run's usage reports.
    assert model.attempts == [1] * result.usage.requests
    assert model.failed == 0
    # …while the tool call behind the carrier was retried: the server's record of it says attempt 2.
    assert max(tool_activity(by_name).attempts) >= 2


async def test_an_item_that_is_out_of_stock_is_not_quoted():
    traced, _ = await ask("Can I order 5 gadgets to Canada? Tell me about stock and shipping.")
    output = traced.result.output

    assert "check_stock" in tool_names(traced.result)
    # Gadgets are out of stock: whatever the model says, it must not invent a price for them.
    assert output.shipping_usd is None or output.shipping_usd == pytest.approx(
        quote_for("gadget", 5, "Canada")
    )
    assert any(
        isinstance(part, ToolCallPart) and part.tool_name == "check_stock"
        for message in traced.result.all_messages()
        for part in message.parts
    )


async def test_the_agent_ran():
    """The span-based check can't see a run inside a workflow, so use the server's own record: the
    activities of an agent are named after it, and its model requests ran and completed."""
    traced, workflow_id = await ask("Is the widget in stock?")
    by_name = await activities(await connect(DeskDeps().temporal_address), workflow_id)
    ran = {name.split("__")[1] for name in by_name if name.startswith("agent__")}
    assert model_requests(by_name).completed >= 1
    assert_every_agent_ran(module, ran | {step.agent for step in traced.result.steps})


async def test_the_demo_script_runs():
    out = await run_as_script("examples.temporal.agent")
    assert "shipping_usd=" in out
    assert "carrier calls" in out
