"""Temporal: a durable agent whose run survives failing tools and crashing workers.

Use this pattern when:
- A run takes long enough, or touches enough flaky systems, that a crash or an outage partway through
  would otherwise mean starting over (and paying for the model calls again)
- Tools call things that fail transiently (a carrier's API, a payment provider, a slow database)
- You want a run you can start, leave, and come back to: it is resumed by any worker, not lost

How it works: with the `TemporalDurability` capability, every model request and every tool call runs
as a Temporal *activity*, and the agent loop itself runs as a Temporal *workflow* whose history is
stored on the Temporal server. Two things follow, and the tests prove both:

    a tool raises            Temporal retries that activity (the policy is `RETRY_POLICY`); the model
                             is never asked again, and never sees the failure
    the worker dies          another worker picks the workflow up and replays its history: the model
                             requests and tool calls that already finished are not run again

The server is a service (`service/`, started by Docker Compose). Its address is a dependency
(`DeskDeps.temporal_address`, read from TEMPORAL_ADDRESS). `run_order_desk` starts a worker *in this
process* and runs one workflow, which keeps the example in one file. In a real system the worker is
its own long-running process; see the README for the three lines that split it out.

The stock and prices are invented. The shipping carrier fails the first time it is asked about each
shipment (`CARRIER.fail_first`) so the retry is visible; replace it with your own tools.
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.durable_exec.temporal import (
    LogfirePlugin,
    PydanticAIPlugin,
    PydanticAIWorkflow,
    TemporalDurability,
)
from pydantic_ai.usage import UsageLimits
from temporalio import workflow
from temporalio.client import Client, WorkflowFailureError
from temporalio.common import RetryPolicy
from temporalio.exceptions import TimeoutError as WorkflowTimeoutError
from temporalio.worker import Worker
from temporalio.workflow import ActivityConfig

# Temporal runs a workflow in a sandbox that re-executes this module, and the sandbox forbids what
# the template's own modules do at import time (reading .env, for one). Importing them as
# "passed through" makes the sandbox reuse the ones already loaded instead of running them again.
with workflow.unsafe.imports_passed_through():
    from agent.config import settings
    from agent.logging import agent_label, configure_logging, get_logger
    from agent.prompts.templates import load_prompt
    from agent.runs import RunResult, Step

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

USAGE_LIMITS = UsageLimits(
    request_limit=8, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)

# --- Temporal settings ---
DEFAULT_ADDRESS = (
    "127.0.0.1:7233"  # where the service listens when started with `docker compose up`
)
TASK_QUEUE = "order-desk"  # the queue the worker polls and the workflow is started on
RUN_TIMEOUT = timedelta(
    minutes=2
)  # a whole run; a workflow that never finishes is failed, not hung
# Every activity (a model request or a tool call) gets this timeout and this retry policy.
RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(milliseconds=200), backoff_coefficient=1.5, maximum_attempts=5
)
ACTIVITY_CONFIG = ActivityConfig(
    start_to_close_timeout=timedelta(seconds=30), retry_policy=RETRY_POLICY
)


def temporal_address_from_env() -> str:
    return os.environ.get("TEMPORAL_ADDRESS", DEFAULT_ADDRESS)


# --- The data ---
Sku = Literal["widget", "gadget", "gizmo"]
Country = Literal["Norway", "Germany", "Canada"]

STOCK = {"widget": 120, "gadget": 0, "gizmo": 8}
BASE_SHIPPING_USD = {"Norway": 14.00, "Germany": 9.50, "Canada": 18.00}
PER_ITEM_USD = {"widget": 0.40, "gadget": 1.25, "gizmo": 2.10}


def quote_for(sku: str, quantity: int, country: str) -> float:
    """What the carrier charges: a base rate for the country plus a rate per item."""
    return round(BASE_SHIPPING_USD[country] + PER_ITEM_USD[sku] * quantity, 2)


class CarrierUnavailable(ConnectionError):
    """The carrier's API did not answer. An ordinary exception: Temporal retries the activity."""


@dataclass
class Carrier:
    """A shipping carrier's API that is down the first `fail_first` times for each shipment.

    `attempts` records every call as (shipment, succeeded), so a test can see the retries that
    really happened. Replace this with your own client; the agent only sees the tool.
    """

    fail_first: int = 1
    attempts: list[tuple[str, bool]] = field(default_factory=list)

    def reset(self) -> None:
        self.attempts.clear()

    async def quote(self, sku: str, quantity: int, country: str) -> float:
        shipment = f"{quantity}x{sku}->{country}"
        earlier = sum(1 for key, _ in self.attempts if key == shipment)
        if earlier < self.fail_first:
            self.attempts.append((shipment, False))
            raise CarrierUnavailable(f"carrier API timed out quoting {shipment}")
        self.attempts.append((shipment, True))
        return quote_for(sku, quantity, country)


CARRIER = Carrier()


# --- Dependencies ---
@dataclass
class DeskDeps:
    """Runtime dependencies for the order desk. They are serialized into every activity."""

    temporal_address: str = field(default_factory=temporal_address_from_env)


class TemporalUnavailable(Exception):
    """The Temporal server could not be reached."""


class RunTimedOut(Exception):
    """The workflow did not finish within its time limit."""


# --- Output type ---
class Answer(BaseModel):
    # `result` is the conventional output field in these examples; the generated
    # eval starter reads it when present (see evals/helpers.py).
    result: str
    shipping_usd: float | None = None


# --- Agent ---
# The capability makes the agent durable. The agent is built here, at module level, because the
# worker must know its activities before a workflow runs; model requests and tool calls are routed
# through activities, so they run on the worker, not inside the workflow.
order_desk_agent: Agent[DeskDeps, Answer] = Agent(
    settings.model,
    name=LABEL,
    output_type=Answer,
    deps_type=DeskDeps,
    capabilities=[
        RaiseContentFilterError(),
        TemporalDurability(activity_config=ACTIVITY_CONFIG),
    ],
    instructions=load_prompt("temporal"),
)


@order_desk_agent.tool_plain
async def check_stock(sku: Sku) -> int:
    """How many units of an item are in stock."""
    return STOCK[sku]


@order_desk_agent.tool_plain
async def shipping_quote(
    sku: Sku, quantity: Annotated[int, Field(ge=1, le=100)], country: Country
) -> float:
    """The carrier's shipping cost in US dollars for `quantity` units of an item to a country."""
    return await CARRIER.quote(sku, quantity, country)


# --- Workflow ---
@workflow.defn
class OrderDeskWorkflow(PydanticAIWorkflow):
    """One agent run as a durable workflow. Its history is kept by the Temporal server."""

    __pydantic_ai_agents__ = [order_desk_agent]

    @workflow.run
    async def run(self, user_input: str, deps: DeskDeps) -> AgentRunResult[Answer]:
        # The return annotation matters: it is what makes the client receive a real AgentRunResult.
        return await order_desk_agent.run(user_input, deps=deps, usage_limits=USAGE_LIMITS)


# --- Running it ---
async def connect(address: str) -> Client:
    """A client for the Temporal server at `address`, able to carry Pydantic AI's types.

    `LogfirePlugin` sends Temporal's own spans (the workflow, and each model and tool activity) to
    Logfire; without it a trace of a run shows none of them. It also keeps replays from emitting
    spans a second time. Pydantic AI's `invoke_agent` span is not among them: the run happens in
    a workflow and an activity, not in the caller, so the server's history is the record of it.
    """
    try:
        return await Client.connect(address, plugins=[PydanticAIPlugin(), LogfirePlugin()])
    except RuntimeError as exc:  # temporalio reports a refused connection as a RuntimeError
        raise TemporalUnavailable(
            f"No Temporal server at {address}. Start the service (`docker compose up -d --wait` "
            "in the directory with its docker-compose.yml) and set TEMPORAL_ADDRESS to the "
            "address Docker published, or point TEMPORAL_ADDRESS at your own Temporal server."
        ) from exc


def make_worker(client: Client, **options: object) -> Worker:
    """A worker that runs the order desk's workflow and the activities of its agent."""
    return Worker(client, task_queue=TASK_QUEUE, workflows=[OrderDeskWorkflow], **options)  # type: ignore[arg-type]


async def run_order_desk(
    user_input: str,
    deps: DeskDeps | None = None,
    *,
    workflow_id: str | None = None,
    timeout: timedelta = RUN_TIMEOUT,
) -> RunResult[Answer]:
    """Answer an order question as a Temporal workflow, with a worker running in this process.

    Returns:
        A RunResult: `.output` is the `Answer`; its one step's result is the workflow's own result.

    Raises:
        TemporalUnavailable: When the server can't be reached.
        RunTimedOut: When the workflow does not finish within `timeout`.
    """
    if deps is None:
        deps = DeskDeps()
    logger.info(
        "Running order desk", extra={"user_input": user_input, "server": deps.temporal_address}
    )
    client = await connect(deps.temporal_address)
    async with make_worker(client):
        try:
            result: AgentRunResult[Answer] = await client.execute_workflow(
                OrderDeskWorkflow.run,
                args=[user_input, deps],
                id=workflow_id or f"order-desk-{uuid4()}",
                task_queue=TASK_QUEUE,
                # Temporal retries a workflow task that fails forever, so a bug in workflow code
                # would hang the caller. The execution timeout turns that into a failure.
                execution_timeout=timeout,
            )
        except WorkflowFailureError as exc:
            if isinstance(exc.cause, WorkflowTimeoutError):
                raise RunTimedOut(f"the workflow did not finish within {timeout}") from exc
            raise
    return RunResult(
        output=result.output, steps=[Step(agent=LABEL, result=result)], usage=result.usage
    )


def main() -> None:
    configure_logging()
    question = "I'd like to order 3 gizmos for Norway. Are they in stock, and what is the shipping?"
    run = asyncio.run(run_order_desk(question))
    print(run.output)
    print(f"{len(CARRIER.attempts)} carrier calls: {CARRIER.attempts}")


if __name__ == "__main__":
    # Temporal cannot run a workflow that is defined in `__main__` (its sandbox imports the workflow's
    # module by name), and the agent's name would differ too. So run this module again under its real
    # name. That is why it is started with `python -m examples.temporal.agent`, not by file path.
    import importlib

    importlib.import_module(__spec__.name).main()
