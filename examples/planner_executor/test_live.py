"""Live check: a real model plans, real executors look cities up, and the answer is right. `-m eval`.

The expected answers are worked out here from the data, not read from the model's output, and the
plan is checked for its shape (independent lookups together, a step that needs them after), not for
exact wording, so another model that plans differently still passes.
"""

import pytest

from evals.trace import traced_run
from examples.live_support import assert_every_agent_ran, run_as_script
from examples.planner_executor import agent as module
from examples.planner_executor.agent import CITIES, density

pytestmark = pytest.mark.eval

DENSEST_QUESTION = (
    "Which of Brindlemoor, Quillhaven and Tarnby is the most densely populated, "
    "and what is its density in people per km²?"
)


async def ask(question: str):
    """Run with a fresh ledger: returns the traced run and the deps it used."""
    deps = module.PlanDeps()

    async def helper(text: str):
        return await module.run_planner_executor(text, deps)

    return await traced_run(helper, question), deps


def looked_up(deps: module.PlanDeps) -> set[str]:
    return {name.strip().lower() for name in deps.calls}


@pytest.fixture(scope="module")
async def densest():
    return await ask(DENSEST_QUESTION)


@pytest.fixture(scope="module")
async def percent_larger():
    return await ask(
        "How much larger, in percent, is the population of Ashwick than Brindlemoor's?"
    )


@pytest.fixture(scope="module")
async def missing_city():
    return await ask("What is the combined population of Quillhaven and Atlantis?")


async def test_the_answer_matches_what_the_data_says(densest):
    traced, _ = densest
    output = traced.result.output
    best = max(CITIES.values(), key=density)  # Quillhaven, 1200.0: no tie for first place

    assert output.subject == best.name
    assert output.value == pytest.approx(density(best), abs=0.1)
    assert output.failed == [] and output.skipped == []


async def test_every_city_in_the_question_was_really_looked_up(densest):
    _, deps = densest
    assert {"brindlemoor", "quillhaven", "tarnby"} <= looked_up(deps)


async def test_the_plan_groups_independent_lookups_and_has_a_step_that_needs_them(densest):
    traced, _ = densest
    output = traced.result.output
    plan = output.plan

    assert len(plan.steps) >= 3
    assert len(output.waves[0]) >= 2  # lookups that need nothing ran together, not one by one
    assert any(step.depends_on for step in plan.steps)  # something was left to do with the lookups
    assert {s for wave in output.waves for s in wave} == {step.id for step in plan.steps}


async def test_each_agent_ran_in_the_order_the_pattern_says(densest):
    traced, _ = densest
    agents = [step.agent for step in traced.result.steps]
    assert agents[0] == "planner_executor.planner"
    assert agents[-1] == "planner_executor.synthesizer"
    assert agents[1:-1] and set(agents[1:-1]) == {"planner_executor.executor"}
    assert "get_city" in traced.tools_called


async def test_a_calculation_that_needs_two_lookups_is_exact(percent_larger):
    traced, deps = percent_larger
    ashwick, brindlemoor = CITIES["Ashwick"].population, CITIES["Brindlemoor"].population
    expected = (ashwick - brindlemoor) / brindlemoor * 100  # 150.0

    assert traced.result.output.value == pytest.approx(expected, abs=0.1)
    assert {"ashwick", "brindlemoor"} <= looked_up(deps)


async def test_a_city_that_does_not_exist_is_reported_not_invented(missing_city):
    traced, deps = missing_city
    output = traced.result.output

    assert "atlantis" in looked_up(deps)  # an executor really asked the tool, and was told no
    assert "Atlantis" in output.result  # the answer says what it could not do
    # No invented total: either no figure, or only the one city that does exist.
    assert output.value is None or output.value == pytest.approx(CITIES["Quillhaven"].population)


async def test_every_agent_ran(densest, percent_larger, missing_city):
    ran = densest[0].agents_ran | percent_larger[0].agents_ran | missing_city[0].agents_ran
    assert_every_agent_ran(module, ran)


async def test_the_demo_script_runs():
    out = await run_as_script("examples.planner_executor.agent")
    assert "waves:" in out and "cities looked up:" in out
