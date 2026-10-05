"""Human in the loop: pause a risky action until a person approves it.

Use this pattern when:
- The agent can take actions with real consequences (money, deletions, messages)
- Some of those actions should wait for a human, and others are fine to run alone
- Impossible requests should be rejected without bothering anyone

How it works:
    1. `issue_refund` is a tool whose arguments are checked first (`args_validator`): an unknown
       order, a shipped order or an amount over the total is rejected on the spot, and the human is
       never asked about it
    2. A refund above AUTO_APPROVE_LIMIT_USD raises `ApprovalRequired`: the run *pauses* and returns
       `DeferredToolRequests` instead of acting
    3. `run_refunds` asks an approver (a human, a policy, a ticket queue) about each request, then
       resumes the same run with their decisions; a denial is explained to the model
    4. An output validator checks that what the model says happened is what the ledger shows

`deps.refunds` is the ledger and the ground truth for whether anything really happened, which is
what the tests check, rather than trusting what the model says.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel
from pydantic_ai import (
    Agent,
    ApprovalRequired,
    DeferredToolRequests,
    DeferredToolResults,
    ModelRetry,
    RunContext,
    ToolDenied,
    ToolFailed,
)
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.prompts.templates import load_prompt
from agent.runs import Flow, RunResult

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# Each approval round is another model request, so leave headroom for a couple of rounds.
USAGE_LIMITS = UsageLimits(
    request_limit=12, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)

AUTO_APPROVE_LIMIT_USD = 25.0  # refunds up to this run without a human
MAX_APPROVAL_ROUNDS = 3  # a run that keeps asking for approval is stopped


# --- The business data ---
@dataclass(frozen=True)
class Order:
    id: str
    item: str
    total: float
    status: str  # "delivered" or "shipped"


ORDERS: dict[str, Order] = {
    "A100": Order("A100", "Trailhead boots", 84.50, "delivered"),
    "A101": Order("A101", "Wool socks", 18.00, "delivered"),
    "A102": Order("A102", "Summit pack", 129.00, "shipped"),
}


@dataclass(frozen=True)
class Refund:
    order_id: str
    amount: float
    reason: str


# --- Approvers: how a decision gets made ---
# An approver is shown the pending tool call and returns True to approve, or a string explaining
# why it is denied (the model is told that string).
Approver = Callable[[ToolCallPart], Awaitable[bool | str]]


async def deny_all(call: ToolCallPart) -> bool | str:
    """The safe default: with no approver configured, nothing risky happens."""
    return "No approver is configured, so this action was not approved."


async def approve_all(call: ToolCallPart) -> bool | str:
    """Approve everything. For demos and tests; never as a production default."""
    return True


async def console_approver(call: ToolCallPart) -> bool | str:
    """Ask a person at the terminal."""
    args = call.args_as_dict()
    print(f"\nApproval needed: {call.tool_name}({args})")
    answer = await asyncio.to_thread(input, "Approve? [y/N] ")
    return True if answer.strip().lower() in {"y", "yes"} else "The reviewer declined."


# --- Dependencies ---
@dataclass
class RefundDeps:
    """Runtime dependencies for the refunds agent."""

    orders: dict[str, Order] = field(default_factory=lambda: dict(ORDERS))
    approver: Approver = deny_all
    refunds: list[Refund] = field(default_factory=list)  # the ledger: what really happened
    decisions: list[tuple[str, bool]] = field(default_factory=list)  # (order id, approved?) asked


# --- Output type ---
class RefundOutput(BaseModel):
    # `result` is the conventional output field in these examples; the generated
    # eval starter reads it when present (see evals/helpers.py).
    result: str
    refunded: bool


# --- Agent ---
# DeferredToolRequests in the output type is what lets a run pause for approval.
refund_agent: Agent[RefundDeps, RefundOutput | DeferredToolRequests] = Agent(
    settings.model,
    name=LABEL,
    output_type=[RefundOutput, DeferredToolRequests],
    deps_type=RefundDeps,
    capabilities=[RaiseContentFilterError()],
    instructions=load_prompt("human_in_the_loop"),  # prompts/…; copied to agent/prompts/<name>.txt
)


# --- Tools ---
@refund_agent.tool
async def lookup_order(ctx: RunContext[RefundDeps], order_id: str) -> str:
    """Look up an order: its item, total and status.

    Args:
        order_id: The order id, such as "A100".

    Raises:
        ToolFailed: When there is no such order.
    """
    order = ctx.deps.orders.get(order_id.strip().upper())
    if order is None:
        raise ToolFailed(f"There is no order {order_id!r}. Ask the customer to check the number.")
    return f"Order {order.id}: {order.item}, total ${order.total:.2f}, status {order.status}."


def check_refund(
    ctx: RunContext[RefundDeps], order_id: str, amount_usd: float, reason: str
) -> None:
    """Runs before the tool and before any approval, so a human is only asked about real requests.

    Raises ToolFailed (nothing to find or do), ModelRetry (the model can correct the amount), or
    ApprovalRequired (valid, but a person must say yes).
    """
    order = ctx.deps.orders.get(order_id.strip().upper())
    if order is None:
        raise ToolFailed(f"There is no order {order_id!r}.")
    if order.status != "delivered":
        raise ToolFailed(
            f"Order {order.id} is {order.status}, not delivered, so it cannot be refunded."
        )
    if any(refund.order_id == order.id for refund in ctx.deps.refunds):
        raise ToolFailed(f"Order {order.id} has already been refunded.")
    if not 0 < amount_usd <= order.total:
        raise ModelRetry(
            f"The refund must be more than $0 and at most the order total of ${order.total:.2f}."
        )
    if amount_usd > AUTO_APPROVE_LIMIT_USD and not ctx.tool_call_approved:
        raise ApprovalRequired()  # pauses the run; the tool does not execute yet


@refund_agent.tool(args_validator=check_refund)
async def issue_refund(
    ctx: RunContext[RefundDeps], order_id: str, amount_usd: float, reason: str
) -> str:
    """Refund part or all of a delivered order. Larger refunds wait for a person's approval.

    Args:
        order_id: The order id, such as "A100".
        amount_usd: The amount to refund, at most the order total.
        reason: Why the customer is asking, in a few words.
    """
    refund = Refund(order_id.strip().upper(), amount_usd, reason)
    ctx.deps.refunds.append(refund)  # the only place money moves
    logger.info("Refund issued", extra={"order": refund.order_id, "amount": amount_usd})
    return f"Refunded ${amount_usd:.2f} on order {refund.order_id}."


# --- Honest reporting ---
@refund_agent.output_validator
def check_the_claim_matches_the_ledger(
    ctx: RunContext[RefundDeps], output: RefundOutput | DeferredToolRequests
) -> RefundOutput | DeferredToolRequests:
    """The model may not say a refund happened unless the ledger shows one (or vice versa)."""
    if isinstance(output, RefundOutput) and output.refunded != bool(ctx.deps.refunds):
        raise ModelRetry(
            f"You set refunded={output.refunded}, but issue_refund has "
            f"{'run' if ctx.deps.refunds else 'not run'}. Report what actually happened."
        )
    return output


class ApprovalLoopError(Exception):
    """The agent kept asking for approval instead of finishing."""


async def run_refunds(user_input: str, deps: RefundDeps | None = None) -> RunResult[RefundOutput]:
    """Handle a refund request, pausing for approval where one is needed.

    Returns:
        A RunResult: `.output` is the final `RefundOutput`. `.steps` has one step per run of the
        agent: the first, then one for each time it resumed after an approval round.

    Raises:
        ApprovalLoopError: When the agent is still waiting for approval after
            MAX_APPROVAL_ROUNDS rounds.
    """
    if deps is None:
        deps = RefundDeps()
    logger.info("Running refunds agent", extra={"user_input": user_input})
    flow = Flow(USAGE_LIMITS)
    result = await flow.run(refund_agent, user_input, deps=deps)

    for _ in range(MAX_APPROVAL_ROUNDS):
        if not isinstance(result.output, DeferredToolRequests):
            return flow.finish(result.output)

        decisions = DeferredToolResults()
        for call in result.output.approvals:
            verdict = await deps.approver(call)
            approved = verdict is True
            deps.decisions.append((str(call.args_as_dict().get("order_id")), approved))
            decisions.approvals[call.tool_call_id] = True if approved else ToolDenied(str(verdict))
        # Resume the same conversation with the decisions; there is no new prompt.
        result = await flow.run(
            refund_agent,
            None,
            deps=deps,
            message_history=result.all_messages(),
            deferred_tool_results=decisions,
        )

    if isinstance(result.output, DeferredToolRequests):
        raise ApprovalLoopError(f"Still waiting for approval after {MAX_APPROVAL_ROUNDS} rounds")
    return flow.finish(result.output)


if __name__ == "__main__":
    import sys

    configure_logging()
    # A person at a terminal is asked; piped or scripted, approve so the demo completes.
    approver = console_approver if sys.stdin.isatty() else approve_all
    demo = RefundDeps(approver=approver)
    result = asyncio.run(
        run_refunds("Order A100 arrived with a broken sole. Refund the full $84.50.", demo)
    )
    print(result.output, "| ledger:", demo.refunds)
