"""Live check: the model solves real questions by writing code, and the numbers are exactly right.

The tool-call ledger (`deps.calls`) is the ground truth for what the model's code did on the host,
and the answers are compared with figures worked out independently from the data. Needs
pydantic-ai-harness (declared in example.toml); run by scripts/release_check.py in the example's own
environment. Run with `pytest -m eval`.
"""

import pytest

pytest.importorskip("pydantic_ai_harness", reason="needs pydantic-ai-harness[code-mode]")

from evals.trace import traced_run  # noqa: E402
from examples.code_mode import agent as module  # noqa: E402
from examples.live_support import assert_every_agent_ran, run_as_script  # noqa: E402

pytestmark = pytest.mark.eval

CENT = 0.01


def worked_out(employee_id: str, category: str) -> float:
    """The right answer, from the data, without the model or the sandbox."""
    return round(
        sum(
            x.amount * module.RATES_TO_USD[x.currency]
            for x in module.EXPENSES
            if x.employee_id == employee_id and x.category == category
        ),
        2,
    )


async def ask(question: str):
    """Run the agent with a fresh ledger: returns the traced run and the deps it used."""
    deps = module.ExpenseDeps()

    async def helper(text: str):
        return await module.run_expenses(text, deps)

    return await traced_run(helper, question), deps


def fetched(deps: module.ExpenseDeps) -> set[str]:
    """The expense ids the model's code actually looked up on the host."""
    return {arg for name, arg in deps.calls if name == "get_expense"}


@pytest.fixture(scope="module")
async def travel():
    return await ask("What is the total of Maya's travel expenses, in US dollars?")


@pytest.fixture(scope="module")
async def meals():
    return await ask(
        "Which employee spent the most on meals, in US dollars? Give their id and their meal total."
    )


@pytest.fixture(scope="module")
async def one_expense():
    return await ask("What is expense X203 worth in US dollars?")


async def test_a_total_across_currencies_is_exactly_right_and_came_from_code(travel):
    traced, _ = travel
    assert "run_code" in traced.tools_called  # the sandbox's one tool: the work was done in code
    output = traced.result.output
    assert output.amount_usd == pytest.approx(worked_out("E2", "travel"), abs=CENT)  # 1520.12
    assert output.subject == "E2"


async def test_the_code_really_fetched_every_record_it_needed(travel):
    _, deps = travel
    mayas_travel = {
        x.id for x in module.EXPENSES if x.employee_id == "E2" and x.category == "travel"
    }
    assert mayas_travel <= fetched(deps)  # no expense was skipped or guessed


async def test_comparing_every_employee_picks_the_right_one(meals):
    traced, deps = meals
    output = traced.result.output
    assert (
        output.subject == "E3"
    )  # not the employee with the most meals, but the largest in dollars
    assert output.amount_usd == pytest.approx(worked_out("E3", "meals"), abs=CENT)  # 296.78
    every_meal = {x.id for x in module.EXPENSES if x.category == "meals"}
    assert every_meal <= fetched(deps)  # all three employees' meals, converted correctly


async def test_a_single_conversion_is_exact(one_expense):
    traced, _ = one_expense
    expected = round(18200 * module.RATES_TO_USD["JPY"], 2)  # 121.94
    assert traced.result.output.amount_usd == pytest.approx(expected, abs=CENT)
    assert traced.result.output.subject == "X203"


async def test_one_or_two_model_requests_do_the_work_of_dozens_of_tool_calls(travel, meals):
    """The reason for the pattern. Plain tool calling needs a model round trip per step."""
    for traced, deps in (travel, meals):
        requests = traced.result.usage.requests
        assert len(deps.calls) >= 10
        assert len(deps.calls) >= 3 * requests, f"{len(deps.calls)} calls in {requests} requests"


async def test_the_sandbox_was_the_only_way_in(travel, meals, one_expense):
    """The model was offered `run_code` and nothing else, so every host call came from its code."""
    for traced, deps in (travel, meals, one_expense):
        assert traced.tools_called.count("run_code") >= 1
        assert deps.calls  # and the code did reach the real tools


async def test_the_agent_ran(travel, meals, one_expense):
    ran = travel[0].agents_ran | meals[0].agents_ran | one_expense[0].agents_ran
    assert_every_agent_ran(module, ran)


async def test_the_demo_script_runs():
    out = await run_as_script("examples.code_mode.agent")
    assert "amount_usd=" in out and "tool calls in" in out
