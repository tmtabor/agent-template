"""The refund tool's validation, the approval pause/resume loop, and the honesty check — offline.

The ledger (`deps.refunds`) is the ground truth throughout: these tests check what really happened,
not what the model said.
"""

import builtins

import pytest
from pydantic_ai import ApprovalRequired, DeferredToolRequests, ModelRetry, RunContext, ToolFailed
from pydantic_ai.messages import (
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from examples.human_in_the_loop import agent as module
from examples.human_in_the_loop.agent import (
    AUTO_APPROVE_LIMIT_USD,
    ORDERS,
    ApprovalLoopError,
    Refund,
    RefundDeps,
    RefundOutput,
    approve_all,
    check_refund,
    check_the_claim_matches_the_ledger,
    console_approver,
    deny_all,
    issue_refund,
    lookup_order,
    refund_agent,
    run_refunds,
)


def ctx(deps: RefundDeps | None = None, approved: bool = False) -> RunContext[RefundDeps]:
    return RunContext(
        deps=deps or RefundDeps(), model=TestModel(), usage=RunUsage(), tool_call_approved=approved
    )


# --- lookup_order ---


async def test_an_order_is_described_whatever_the_case_of_its_id():
    text = await lookup_order(ctx(), " a100 ")
    assert text == "Order A100: Trailhead boots, total $84.50, status delivered."


async def test_an_unknown_order_is_a_terminal_failure():
    with pytest.raises(ToolFailed, match="no order 'Z9'"):
        await lookup_order(ctx(), "Z9")


# --- check_refund: runs before the tool and before any approval ---


def check(order="A100", amount=84.50, deps=None, approved=False):
    check_refund(ctx(deps, approved), order, amount, "broken")


def test_an_unknown_order_is_rejected_before_anyone_is_asked():
    with pytest.raises(ToolFailed, match="no order"):
        check(order="nope")


def test_an_order_that_has_not_been_delivered_cannot_be_refunded():
    with pytest.raises(ToolFailed, match="shipped, not delivered"):
        check(order="A102", amount=10)


def test_an_order_cannot_be_refunded_twice():
    deps = RefundDeps(refunds=[Refund("A101", 18.0, "x")])
    with pytest.raises(ToolFailed, match="already been refunded"):
        check(order="A101", amount=5, deps=deps)


@pytest.mark.parametrize("amount", [0, -5, 84.51, 500])
def test_an_amount_outside_zero_to_the_total_asks_the_model_to_correct_it(amount):
    with pytest.raises(ModelRetry, match=r"at most the order total of \$84.50"):
        check(amount=amount)


def test_a_small_refund_needs_no_approval():
    check(order="A100", amount=AUTO_APPROVE_LIMIT_USD)  # at the limit is still automatic


def test_a_larger_refund_pauses_for_approval():
    with pytest.raises(ApprovalRequired):
        check(amount=AUTO_APPROVE_LIMIT_USD + 0.01)


def test_once_approved_the_same_refund_passes():
    check(amount=84.50, approved=True)


# --- issue_refund ---


async def test_issuing_a_refund_records_it_in_the_ledger():
    deps = RefundDeps()
    text = await issue_refund(ctx(deps), " a101", 18.0, "hole")
    assert text == "Refunded $18.00 on order A101."
    assert deps.refunds == [Refund("A101", 18.0, "hole")]


def test_a_deps_object_gets_its_own_copy_of_the_orders_and_denies_by_default():
    deps = RefundDeps()
    deps.orders.pop("A100")
    assert "A100" in ORDERS  # the shared table is untouched
    assert deps.approver is deny_all


# --- Approvers ---


async def test_the_default_approver_declines_with_a_reason_the_model_can_relay():
    verdict = await deny_all(ToolCallPart("issue_refund", {}))
    assert isinstance(verdict, str) and "not approved" in verdict


async def test_approve_all_approves():
    assert await approve_all(ToolCallPart("issue_refund", {})) is True


@pytest.mark.parametrize(
    ("typed", "approved"), [("y", True), (" YES ", True), ("n", False), ("", False)]
)
async def test_the_console_approver_asks_a_person(monkeypatch, capsys, typed, approved):
    monkeypatch.setattr(builtins, "input", lambda prompt: typed)
    call = ToolCallPart("issue_refund", {"order_id": "A100", "amount_usd": 84.5})
    verdict = await console_approver(call)
    assert (verdict is True) == approved
    if not approved:
        assert verdict == "The reviewer declined."
    assert "Approval needed: issue_refund" in capsys.readouterr().out


# --- Honest reporting ---


def claim(refunded: bool, ledger: bool):
    deps = RefundDeps(refunds=[Refund("A100", 1.0, "x")] if ledger else [])
    return check_the_claim_matches_the_ledger(
        ctx(deps), RefundOutput(result="r", refunded=refunded)
    )


def test_a_claim_that_matches_the_ledger_passes():
    assert claim(True, True).refunded and not claim(False, False).refunded


def test_claiming_a_refund_that_never_happened_is_sent_back():
    with pytest.raises(ModelRetry, match="refunded=True, but issue_refund has not run"):
        claim(True, False)


def test_denying_a_refund_that_did_happen_is_sent_back():
    with pytest.raises(ModelRetry, match="refunded=False, but issue_refund has run"):
        claim(False, True)


def test_a_pending_approval_request_passes_straight_through():
    pending = DeferredToolRequests()
    assert check_the_claim_matches_the_ledger(ctx(), pending) is pending


# --- The pause/resume loop, with a scripted model ---


def scripted(*steps: dict, seen: list | None = None):
    """Follow `steps` (a tool call, or the final output); optionally record what each call saw."""
    remaining = list(steps)

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(messages)
        step = remaining.pop(0)
        if "tool" in step:
            return ModelResponse(parts=[ToolCallPart(step["tool"], step["args"])])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, step["output"])])

    return FunctionModel(model_fn)


def refund_call(order="A100", amount=84.50):
    return {
        "tool": "issue_refund",
        "args": {"order_id": order, "amount_usd": amount, "reason": "damaged"},
    }


def done(refunded: bool, text="Done."):
    return {"output": {"result": text, "refunded": refunded}}


async def test_an_approved_refund_pauses_then_happens():
    deps = RefundDeps(approver=approve_all)
    model = scripted(refund_call(), done(True, "Refunded."))
    with refund_agent.override(model=model):
        result = await run_refunds("Refund A100", deps)

    assert deps.refunds == [Refund("A100", 84.50, "damaged")]  # it really happened
    assert deps.decisions == [("A100", True)]
    assert result.output == RefundOutput(result="Refunded.", refunded=True)
    assert len(result.steps) == 2  # the run that paused, and the one that resumed


async def test_a_denied_refund_does_not_happen_and_the_model_is_told_why():
    async def decline(call):
        return "Refunds over $25 need a manager."

    deps = RefundDeps(approver=decline)
    seen: list = []
    model = scripted(refund_call(), done(False, "A manager must approve that."), seen=seen)
    with refund_agent.override(model=model):
        result = await run_refunds("Refund A100", deps)

    assert deps.refunds == []  # nothing happened
    assert deps.decisions == [("A100", False)]
    assert result.output.refunded is False
    denied = [
        p
        for m in seen[-1]
        for p in m.parts
        if isinstance(p, ToolReturnPart) and p.outcome == "denied"
    ]
    assert denied and "need a manager" in str(denied[0].content)  # the resumed model saw the reason


async def test_a_small_refund_runs_straight_through_without_asking_anyone():
    deps = RefundDeps(approver=pytest.fail)  # would blow up if anyone were asked
    model = scripted(refund_call("A101", 18.0), done(True, "Refunded $18."))
    with refund_agent.override(model=model):
        result = await run_refunds("Refund the socks", deps)

    assert deps.refunds == [Refund("A101", 18.0, "damaged")]
    assert deps.decisions == []
    assert len(result.steps) == 1


async def test_an_impossible_refund_is_corrected_before_any_human_is_asked():
    deps = RefundDeps(approver=pytest.fail)
    model = scripted(refund_call(amount=500), done(False, "That is more than the order total."))
    with refund_agent.override(model=model):
        result = await run_refunds("Refund $500", deps)

    retries = [p for m in result.all_messages() for p in m.parts if isinstance(p, RetryPromptPart)]
    assert len(retries) == 1 and "order total" in str(retries[0].content)
    assert deps.refunds == [] and deps.decisions == []


async def test_a_read_only_request_never_reaches_the_approval_gate():
    deps = RefundDeps(approver=pytest.fail)
    model = scripted(
        {"tool": "lookup_order", "args": {"order_id": "A102"}}, done(False, "It has shipped.")
    )
    with refund_agent.override(model=model):
        result = await run_refunds("Where is A102?", deps)
    assert deps.refunds == [] and len(result.steps) == 1


async def test_a_model_that_claims_a_refund_that_did_not_happen_is_made_to_correct_itself():
    model = scripted(done(True, "All refunded!"), done(False, "Actually nothing was refunded."))
    with refund_agent.override(model=model):
        result = await run_refunds("Refund A100", RefundDeps())
    assert result.output.refunded is False  # the first, false claim never got out


async def test_a_model_that_keeps_asking_is_stopped_after_the_round_limit():
    asks = [refund_call() for _ in range(module.MAX_APPROVAL_ROUNDS + 1)]
    with refund_agent.override(model=scripted(*asks)), pytest.raises(ApprovalLoopError):
        await run_refunds("Refund A100", RefundDeps())  # default approver declines every time


async def test_the_last_permitted_round_can_still_finish():
    asks = [refund_call() for _ in range(module.MAX_APPROVAL_ROUNDS)]
    with refund_agent.override(model=scripted(*asks, done(False, "Declined."))):
        result = await run_refunds("Refund A100", RefundDeps())
    assert result.output.refunded is False and len(result.steps) == module.MAX_APPROVAL_ROUNDS + 1
