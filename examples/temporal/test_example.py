"""The durable order desk: its tools and carrier, and what Temporal really does when things fail.

The tests that run the workflow need a Temporal server: the release check starts the example's Docker
service and passes its address in TEMPORAL_ADDRESS (see example.toml); without it they are skipped.
(Temporal's own test server downloads a binary at run time, which a hermetic suite must not do.)
They run against the real server with the model replaced by `TestModel`, and check what the *server*
recorded: the workflow's event history says which activities ran, how often, and on which attempt.
Needs temporalio (declared in example.toml), so the module is skipped without it.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("temporalio", reason="needs temporalio")

from pydantic_ai.messages import RetryPromptPart, ToolCallPart, ToolReturnPart  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402
from temporalio.client import WorkflowFailureError  # noqa: E402
from temporalio.exceptions import ApplicationError  # noqa: E402

from agent.runs import RunResult  # noqa: E402
from examples.temporal import agent as module  # noqa: E402
from examples.temporal.agent import (  # noqa: E402
    BASE_SHIPPING_USD,
    PER_ITEM_USD,
    STOCK,
    Answer,
    Carrier,
    CarrierUnavailable,
    DeskDeps,
    RunTimedOut,
    TemporalUnavailable,
    check_stock,
    connect,
    make_worker,
    quote_for,
    run_order_desk,
    shipping_quote,
    temporal_address_from_env,
)


@pytest.fixture(autouse=True)
def fresh_carrier(monkeypatch):
    """Each test gets its own flaky carrier (one failure per shipment), so tests can't leak."""
    carrier = Carrier(fail_first=1)
    monkeypatch.setattr(module, "CARRIER", carrier)
    return carrier


@pytest.fixture
def address() -> str:
    server = os.environ.get("TEMPORAL_ADDRESS")
    if not server:
        pytest.skip("needs the Temporal service running (TEMPORAL_ADDRESS)")
    return server


@pytest.fixture
def deps(address) -> DeskDeps:
    return DeskDeps(temporal_address=address)


# --- The data and the tools, without Temporal ---


def test_a_quote_is_the_countrys_base_rate_plus_a_rate_per_item():
    assert quote_for("gizmo", 3, "Norway") == 20.30  # 14.00 + 3 * 2.10
    assert quote_for("widget", 10, "Germany") == 13.50  # 9.50 + 10 * 0.40
    assert quote_for("gadget", 1, "Canada") == 19.25


def test_every_item_and_country_has_a_price():
    assert set(STOCK) == set(PER_ITEM_USD)
    for country in BASE_SHIPPING_USD:
        for sku in PER_ITEM_USD:
            assert quote_for(sku, 1, country) > BASE_SHIPPING_USD[country]


async def test_the_stock_tool_reports_the_catalogue():
    assert await check_stock("widget") == 120
    assert await check_stock("gadget") == 0


async def test_the_carrier_is_down_for_the_first_try_at_each_shipment_only(fresh_carrier):
    with pytest.raises(CarrierUnavailable):
        await shipping_quote("gizmo", 3, "Norway")
    assert await shipping_quote("gizmo", 3, "Norway") == 20.30  # the retry succeeds
    assert await shipping_quote("gizmo", 3, "Norway") == 20.30  # and keeps succeeding
    with pytest.raises(CarrierUnavailable):  # a different shipment starts out failing again
        await shipping_quote("gizmo", 4, "Norway")
    assert fresh_carrier.attempts == [
        ("3xgizmo->Norway", False),
        ("3xgizmo->Norway", True),
        ("3xgizmo->Norway", True),
        ("4xgizmo->Norway", False),
    ]


async def test_a_carrier_that_never_fails_makes_one_call(fresh_carrier):
    fresh_carrier.fail_first = 0
    assert await fresh_carrier.quote("widget", 2, "Canada") == 18.80
    assert fresh_carrier.attempts == [("2xwidget->Canada", True)]
    fresh_carrier.reset()
    assert fresh_carrier.attempts == []


def test_a_carrier_outage_is_an_ordinary_connection_error():
    """Not a ModelRetry: the model must never see it. Temporal retries the activity instead."""
    assert issubclass(CarrierUnavailable, ConnectionError)


def test_the_address_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("TEMPORAL_ADDRESS", "temporal.internal:7233")
    assert temporal_address_from_env() == "temporal.internal:7233"
    assert DeskDeps().temporal_address == "temporal.internal:7233"
    monkeypatch.delenv("TEMPORAL_ADDRESS")
    assert temporal_address_from_env() == module.DEFAULT_ADDRESS


async def test_an_unreachable_server_is_reported_with_how_to_start_it():
    with pytest.raises(TemporalUnavailable, match="docker compose"):
        await run_order_desk("hello", DeskDeps(temporal_address="127.0.0.1:1"))


# --- Reading the server's record of a run ---


@dataclass
class Activity:
    name: str
    attempts: list[int] = field(default_factory=list)  # the attempt number of each recorded start
    completed: int = 0
    failed: int = 0


async def activities(client, workflow_id: str) -> dict[str, Activity]:
    """What the server recorded: every activity the workflow scheduled, by type, with its attempts."""
    scheduled: dict[int, Activity] = {}
    by_name: dict[str, Activity] = {}
    async for event in client.get_workflow_handle(workflow_id).fetch_history_events():
        kind = event.WhichOneof("attributes")
        if kind == "activity_task_scheduled_event_attributes":
            name = event.activity_task_scheduled_event_attributes.activity_type.name
            scheduled[event.event_id] = by_name.setdefault(name, Activity(name))
        elif kind == "activity_task_started_event_attributes":
            attrs = event.activity_task_started_event_attributes
            scheduled[attrs.scheduled_event_id].attempts.append(attrs.attempt)
        elif kind == "activity_task_completed_event_attributes":
            scheduled[
                event.activity_task_completed_event_attributes.scheduled_event_id
            ].completed += 1
        elif kind == "activity_task_failed_event_attributes":
            scheduled[event.activity_task_failed_event_attributes.scheduled_event_id].failed += 1
    return by_name


def tool_activity(by_name: dict[str, Activity]) -> Activity:
    (found,) = [a for name, a in by_name.items() if name.endswith("__call_tool")]
    return found


def model_requests(by_name: dict[str, Activity]) -> Activity:
    (found,) = [a for name, a in by_name.items() if name.endswith("__model_request")]
    return found


def tool_calls(result: RunResult) -> list[ToolCallPart]:
    return [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_name != "final_result"
    ]


QUESTION = "Order 3 gizmos for Norway: in stock, and what is the shipping?"


# --- A run through Temporal ---


async def test_a_run_goes_through_the_real_server_and_returns_a_normal_result(deps, fresh_carrier):
    result = await run_order_desk(QUESTION, deps)

    assert isinstance(result, RunResult)
    assert isinstance(result.output, Answer)
    assert [step.agent for step in result.steps] == ["temporal"]
    assert result.usage.requests >= 2  # the tool calls, then the answer
    assert {call.tool_name for call in tool_calls(result)} == {"check_stock", "shipping_quote"}


async def test_a_failing_tool_is_retried_and_the_model_never_sees_the_failure(deps, fresh_carrier):
    result = await run_order_desk(QUESTION, deps)

    # The carrier really failed once and then answered, for the shipment the model asked about.
    outcomes = [ok for _, ok in fresh_carrier.attempts]
    assert outcomes == [False, True]
    # The tool result in the history is the carrier's real answer, for the arguments the model used.
    [call] = [c for c in tool_calls(result) if c.tool_name == "shipping_quote"]
    returned = [
        part.content
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "shipping_quote"
    ]
    assert returned == [quote_for(**call.args_as_dict())]
    # Nothing in the conversation asks the model to retry or mentions the outage.
    assert not [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]


async def test_the_server_recorded_the_retry_and_no_repeated_model_request(deps, fresh_carrier):
    workflow_id = f"test-retry-{uuid.uuid4()}"
    result = await run_order_desk(QUESTION, deps, workflow_id=workflow_id)
    by_name = await activities(await connect(deps.temporal_address), workflow_id)

    # Two tool calls, two activities. The server records the attempt that produced each result: the
    # stock check on its first try, the carrier call on its second (the failed first try is not an
    # event of its own; the carrier's own ledger, checked above, shows it).
    tools = tool_activity(by_name)
    assert sorted(tools.attempts) == [1, 2]
    assert tools.completed == 2
    assert tools.failed == 0

    model = model_requests(by_name)
    # Every model request ran exactly once, even though a tool failed in between.
    assert model.attempts == [1] * result.usage.requests
    assert model.completed == result.usage.requests
    assert model.failed == 0


async def test_a_tool_that_keeps_failing_is_retried_to_the_limit_then_the_run_fails(
    deps, fresh_carrier
):
    fresh_carrier.fail_first = 99
    workflow_id = f"test-exhausted-{uuid.uuid4()}"

    with pytest.raises(WorkflowFailureError):
        await run_order_desk(QUESTION, deps, workflow_id=workflow_id)

    assert [ok for _, ok in fresh_carrier.attempts] == [
        False
    ] * module.RETRY_POLICY.maximum_attempts
    by_name = await activities(await connect(deps.temporal_address), workflow_id)
    # The model was asked once for the tool calls and never again: the failure did not loop back to it.
    assert model_requests(by_name).attempts == [1]


async def test_a_tool_that_raises_a_non_retryable_error_is_not_retried(
    deps, fresh_carrier, monkeypatch
):
    """For a failure that retrying cannot fix (a rejected address, a refused payment)."""

    class Rejects(Carrier):
        async def quote(self, sku, quantity, country):
            self.attempts.append((f"{quantity}x{sku}->{country}", False))
            raise ApplicationError("the carrier does not ship there", non_retryable=True)

    rejecting = Rejects()
    monkeypatch.setattr(module, "CARRIER", rejecting)

    with pytest.raises(WorkflowFailureError):
        await run_order_desk(QUESTION, deps)

    assert len(rejecting.attempts) == 1  # one try, not RETRY_POLICY's five


async def test_a_run_that_does_not_finish_in_time_is_failed_not_left_hanging(
    deps, fresh_carrier, monkeypatch
):
    async def stalled(self, *args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(TestModel, "request", stalled)

    with pytest.raises(RunTimedOut, match="did not finish"):
        await run_order_desk(QUESTION, deps, timeout=timedelta(seconds=2))


# --- A worker that dies mid-run ---


@dataclass
class HeldCarrier(Carrier):
    """A carrier whose first call hangs until released, so a test can kill the worker mid-call."""

    in_flight: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def quote(self, sku: str, quantity: int, country: str) -> float:
        if not self.release.is_set():
            self.in_flight.set()
            await self.release.wait()
        return await super().quote(sku, quantity, country)


async def test_a_second_worker_finishes_a_run_whose_first_worker_died(deps, monkeypatch):
    held = HeldCarrier(fail_first=0)
    monkeypatch.setattr(module, "CARRIER", held)
    asked: list[object] = []
    real_request = TestModel.request

    async def counting_request(self, *args, **kwargs):
        asked.append(args[0] if args else None)
        return await real_request(self, *args, **kwargs)

    monkeypatch.setattr(TestModel, "request", counting_request)

    client = await connect(deps.temporal_address)
    workflow_id = f"test-crash-{uuid.uuid4()}"
    async with make_worker(client, graceful_shutdown_timeout=timedelta(0)):
        handle = await client.start_workflow(
            module.OrderDeskWorkflow.run,
            args=[QUESTION, deps],
            id=workflow_id,
            task_queue=module.TASK_QUEUE,
            execution_timeout=timedelta(seconds=90),
        )
        await asyncio.wait_for(
            held.in_flight.wait(), 30
        )  # the model has answered; a tool is mid-call
        asked_before_crash = len(asked)
    # The first worker is gone and the call it was making was cancelled. The workflow is still open.
    assert not held.release.is_set()
    assert asked_before_crash == 1

    held.release.set()
    async with make_worker(client):
        result = await asyncio.wait_for(handle.result(), 60)

    assert isinstance(result.output, Answer)
    # The second worker did not ask the model what to do again: the first answer was in the history.
    assert len(asked) == result.usage.requests == 2
    by_name = await activities(client, workflow_id)
    assert model_requests(by_name).attempts == [1, 1]
    assert max(tool_activity(by_name).attempts) >= 2  # the interrupted tool call was run again


# The worker as its own process (what the README tells you to run in production), killed outright.
WORKER_PROCESS = """
import asyncio, os, pathlib
from examples.temporal import agent as m

class Hangs(m.Carrier):
    async def quote(self, sku, quantity, country):
        pathlib.Path(os.environ["IN_FLIGHT"]).write_text("the carrier call has started")
        await asyncio.sleep(3600)

m.CARRIER = Hangs()

async def main():
    client = await m.connect(os.environ["TEMPORAL_ADDRESS"])
    await m.make_worker(client).run()

asyncio.run(main())
"""
REPO = Path(__file__).resolve().parents[2]


async def test_a_run_survives_its_worker_process_being_killed_outright(
    deps, fresh_carrier, tmp_path
):
    """SIGKILL, not a tidy shutdown: nothing is reported to the server, which only notices when the
    activity's timeout passes (so this takes about as long as ACTIVITY_CONFIG's)."""
    fresh_carrier.fail_first = 0
    in_flight = tmp_path / "in_flight"
    worker = subprocess.Popen(
        [sys.executable, "-c", WORKER_PROCESS],
        cwd=REPO,
        env={
            **os.environ,
            "AGENT_MODEL": "test",
            "TEMPORAL_ADDRESS": deps.temporal_address,
            "IN_FLIGHT": str(in_flight),
            "PYTHONPATH": str(REPO),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    client = await connect(deps.temporal_address)
    workflow_id = f"test-sigkill-{uuid.uuid4()}"
    try:
        handle = await client.start_workflow(
            module.OrderDeskWorkflow.run,
            args=[QUESTION, deps],
            id=workflow_id,
            task_queue=module.TASK_QUEUE,
            execution_timeout=timedelta(minutes=3),
        )
        for _ in range(600):  # up to 60 s for the worker to start and reach the carrier call
            if in_flight.exists() or worker.poll() is not None:
                break
            await asyncio.sleep(0.1)
        assert in_flight.exists(), (
            f"the worker never reached the tool call: {worker.stderr.read()[-1500:]}"
        )
    finally:
        worker.kill()
        worker.wait(timeout=10)
        worker.stderr.close()

    async with make_worker(client):  # a new worker, in this process, with a working carrier
        result = await asyncio.wait_for(handle.result(), 120)

    assert isinstance(result.output, Answer)
    by_name = await activities(client, workflow_id)
    # The model request that finished before the kill ran once; it was not repeated by the new worker.
    assert model_requests(by_name).attempts == [1] * result.usage.requests == [1, 1]
    # The tool call that was in flight when the worker died was started again, by the new one.
    assert max(tool_activity(by_name).attempts) >= 2
