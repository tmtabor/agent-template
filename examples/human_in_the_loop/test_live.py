"""Live check: approvals pause and resume a real run, and the ledger shows what really happened.

The ledger (`deps.refunds`) is the ground truth. What the model *says* is checked against it, never
the other way round. Run with `pytest -m eval`.
"""

import pytest

from evals.trace import traced_run
from examples.human_in_the_loop import agent as module
from examples.live_support import assert_every_agent_ran, run_as_script

pytestmark = pytest.mark.eval


async def decline(call):
    return "Refunds over $25 need a manager."


async def run(prompt: str, approver):
    """Run the agent with a fresh ledger; return the traced run and the deps it used."""
    deps = module.RefundDeps(approver=approver)

    async def helper(text: str):
        return await module.run_refunds(text, deps)

    return await traced_run(helper, prompt), deps


@pytest.fixture(scope="module")
async def approved():
    return await run(
        "Order A100 arrived with a broken sole. Please refund the full $84.50.", module.approve_all
    )


@pytest.fixture(scope="module")
async def denied():
    return await run(
        "Order A100 arrived with a broken sole. Please refund the full $84.50.", decline
    )


@pytest.fixture(scope="module")
async def small():
    return await run(
        "Order A101 had a hole in the socks. Please refund the $18.00.", module.deny_all
    )


@pytest.fixture(scope="module")
async def impossible():
    return await run("Please refund $500 on order A100.", module.approve_all)


@pytest.fixture(scope="module")
async def read_only():
    return await run("What is the status of order A102?", module.approve_all)


async def test_an_approved_refund_really_happens_after_the_run_pauses_and_resumes(approved):
    traced, deps = approved
    assert deps.refunds and deps.refunds[0].order_id == "A100"
    assert deps.refunds[0].amount == pytest.approx(84.50)
    assert deps.decisions == [("A100", True)]  # a person was asked exactly once, and said yes
    assert len(traced.result.steps) == 2  # the run that paused, and the one that resumed
    assert traced.result.output.refunded is True and traced.result.output.result.strip()


async def test_a_denied_refund_does_not_happen_and_the_customer_is_told(denied):
    traced, deps = denied
    assert deps.refunds == []  # money did not move
    assert deps.decisions == [("A100", False)]
    assert traced.result.output.refunded is False  # and the model reports that honestly
    answer = traced.result.output.result.lower()
    assert answer.strip()
    # It must not claim an action it has no way to take (the prompt forbids it).
    assert not [w for w in ("submitted", "escalated", "forwarded") if w in answer], answer


async def test_a_small_refund_goes_through_without_asking_a_person(small):
    traced, deps = small
    assert [r.order_id for r in deps.refunds] == ["A101"]
    assert deps.refunds[0].amount == pytest.approx(18.00)
    assert deps.decisions == []  # the always-deny approver was never consulted
    assert len(traced.result.steps) == 1 and traced.result.output.refunded is True


async def test_an_impossible_refund_is_rejected_before_a_person_is_asked(impossible):
    traced, deps = impossible
    assert deps.refunds == [] and deps.decisions == []  # nobody was bothered, nothing moved
    assert traced.result.output.refunded is False
    assert len(traced.result.steps) == 1


async def test_a_question_about_an_order_changes_nothing(read_only):
    traced, deps = read_only
    assert deps.refunds == [] and deps.decisions == []
    assert "lookup_order" in traced.tools_called
    assert "shipped" in traced.result.output.result.lower()
    assert traced.result.output.refunded is False


async def test_no_run_ever_claimed_something_the_ledger_contradicts(
    approved, denied, small, impossible, read_only
):
    """The honesty check is enforced in code; this confirms it held across every real run."""
    for traced, deps in (approved, denied, small, impossible, read_only):
        assert traced.result.output.refunded == bool(deps.refunds)


async def test_the_agent_ran(approved, denied, small, impossible, read_only):
    ran = set().union(
        *(traced.agents_ran for traced, _ in (approved, denied, small, impossible, read_only))
    )
    assert_every_agent_ran(module, ran)


async def test_the_demo_script_runs():
    out = await run_as_script("examples.human_in_the_loop.agent")
    assert "ledger: [Refund(order_id='A100'" in out  # stdin isn't a terminal, so it auto-approves
