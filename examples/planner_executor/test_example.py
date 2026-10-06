"""The plan check, the scheduling of steps, and what a failed step takes down: all offline.

The three agents run on scripted models, so the planner writes exactly the plan a test wants and the
executors record what they were told and how many were running at once. The tool is the real one.
"""

import asyncio
import re

import pytest
from pydantic_ai import ToolFailed
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from examples.planner_executor.agent import (
    CITIES,
    MAX_STEPS,
    AllStepsFailedError,
    Plan,
    PlanDeps,
    PlanError,
    PlanStep,
    check_plan,
    density,
    executor_agent,
    get_city,
    planner_agent,
    run_planner_executor,
    step_prompt,
    synthesizer_agent,
)

QUESTION = "Which city is densest?"


def plan_of(*steps: tuple[str, list[str]]) -> Plan:
    return Plan(steps=[PlanStep(id=i, instruction=f"do {i}", depends_on=deps) for i, deps in steps])


def prompt_of(messages) -> str:
    return "\n".join(str(p.content) for p in messages[-1].parts if isinstance(p, UserPromptPart))


# --- Scripted agents ---


def planner(plans: list[Plan], seen: list[str] | None = None):
    """Returns the given plans in order, one per request, and records what it was sent."""
    remaining = list(plans)

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(
                " | ".join(
                    str(p.content) for m in messages for p in m.parts if hasattr(p, "content")
                )
            )
        plan = remaining.pop(0)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, plan.model_dump())])

    return FunctionModel(model_fn)


class Executors:
    """A scripted executor that records every prompt, how many ran at once, and who was asked."""

    def __init__(self, fail_on=(), lookups: dict[str, str] | None = None, pause: float = 0.02):
        self.fail_on = set(fail_on)
        self.lookups = lookups or {}  # step id -> a city to look up with the real tool first
        self.pause = pause
        self.prompts: dict[str, str] = {}
        self.running = 0
        self.peak = 0

    @staticmethod
    def step_id(prompt: str) -> str:
        return re.search(r"Your step \((\w+)\)", prompt).group(1)

    @property
    def model(self) -> FunctionModel:
        async def model_fn(messages, info: AgentInfo) -> ModelResponse:
            step = self.step_id(str(messages[0].parts[-1].content))
            returned = any(isinstance(p, ToolReturnPart) for m in messages for p in m.parts)
            if step in self.lookups and not returned:
                return ModelResponse(parts=[ToolCallPart("get_city", {"name": self.lookups[step]})])
            self.prompts[step] = str(messages[0].parts[-1].content)
            self.running += 1
            self.peak = max(self.peak, self.running)
            try:
                await asyncio.sleep(self.pause)  # long enough for siblings to overlap
                if step in self.fail_on:
                    raise RuntimeError(f"{step} blew up")
            finally:
                self.running -= 1
            return ModelResponse(
                parts=[ToolCallPart(info.output_tools[0].name, {"result": f"result of {step}"})]
            )

        return FunctionModel(model_fn)


def synthesizer(seen: list[str]):
    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        seen.append(prompt_of(messages))
        fields = {"result": "the answer", "subject": "Quillhaven", "value": 1200.0}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, fields)])

    return FunctionModel(model_fn)


async def run(plans: list[Plan], executors: Executors, deps: PlanDeps | None = None):
    seen: list[str] = []
    with (
        planner_agent.override(model=planner(plans)),
        executor_agent.override(model=executors.model),
        synthesizer_agent.override(model=synthesizer(seen)),
    ):
        return await run_planner_executor(QUESTION, deps), seen


# --- The data and the tool ---


def test_the_densities_are_what_the_questions_expect():
    assert {name: density(city) for name, city in CITIES.items()} == {
        "Brindlemoor": 700.0,
        "Quillhaven": 1200.0,
        "Tarnby": 300.0,
        "Ashwick": 600.0,
    }
    assert max(CITIES.values(), key=density).name == "Quillhaven"  # no ties for first place


def test_the_tool_finds_a_city_by_any_capitalization_and_records_the_call():
    deps = PlanDeps()
    ctx = type("Ctx", (), {"deps": deps})()
    found = get_city(ctx, "  qUILLhaven ")
    assert found == {
        "name": "Quillhaven",
        "population": 156_000,
        "area_km2": 130.0,
        "founded": 1648,
    }
    assert deps.calls == ["  qUILLhaven "]


def test_the_tool_says_which_cities_exist_when_asked_for_one_that_does_not():
    ctx = type("Ctx", (), {"deps": PlanDeps()})()
    with pytest.raises(ToolFailed, match="no city called 'Atlantis'.*Ashwick, Brindlemoor"):
        get_city(ctx, "Atlantis")


def test_each_run_gets_its_own_cities_and_ledger():
    first, second = PlanDeps(), PlanDeps()
    first.calls.append("Tarnby")
    first.cities.pop("Tarnby")
    assert second.calls == [] and "Tarnby" in second.cities and "Tarnby" in CITIES


# --- The plan check ---


def test_a_good_plan_passes():
    check_plan(plan_of(("a", []), ("b", []), ("c", ["a", "b"])))
    check_plan(plan_of(("only", [])))
    check_plan(plan_of(("a", []), ("b", ["a"]), ("c", ["a"]), ("d", ["b", "c"])))  # a diamond
    check_plan(plan_of(*[(f"s{i}", [f"s{i - 1}"] if i else []) for i in range(MAX_STEPS)]))


@pytest.mark.parametrize(
    ("plan", "message"),
    [
        (Plan(steps=[]), "between 1 and"),
        (plan_of(*[(f"s{i}", []) for i in range(MAX_STEPS + 1)]), "between 1 and"),
        (plan_of(("a", []), ("a", [])), r"unique; repeated: \['a'\]"),
        (plan_of(("a", ["nope"])), r"depends on \['nope'\]"),
        (plan_of(("a", ["a"])), "depends on itself"),
        (plan_of(("a", ["b"]), ("b", ["a"])), r"\['a', 'b'\] wait on each other"),
        (plan_of(("ok", []), ("a", ["c"]), ("b", ["a"]), ("c", ["b"])), r"\['a', 'b', 'c'\] wait"),
        (plan_of(("a", []), ("b", [])), r"\['a', 'b'\] are not used by any other step"),
        (plan_of(("a", []), ("b", []), ("c", ["a"])), r"\['b', 'c'\] are not used"),
        # What the rule is for: two lookups and a "compare them" step that forgot to depend on them.
        (plan_of(("s1", []), ("s2", []), ("s3", [])), r"\['s1', 's2', 's3'\] are not used"),
    ],
)
def test_a_plan_that_cannot_be_carried_out_is_rejected_with_the_reason(plan, message):
    with pytest.raises(PlanError, match=message):
        check_plan(plan)


def test_a_rejected_plan_is_told_what_to_change_not_only_what_is_wrong():
    plan = plan_of(("s1", []), ("s2", []), ("s3", []), ("s4", []))
    with pytest.raises(PlanError) as caught:
        check_plan(plan)
    # The last loose end is offered as the final step, with the others as what it should depend on.
    assert (
        "make 's4' the final step by setting its depends_on to include ['s1', 's2', 's3']"
        in str(caught.value)
    )


def test_the_planner_is_told_what_its_executors_can_do():
    from agent.prompts.templates import load_prompt

    text = load_prompt("planner_executor_planner")
    assert "get_city" in text  # the executor's one tool
    assert "six" in text and MAX_STEPS == 6  # the limit it is told is the one that is enforced


async def test_a_rejected_plan_is_sent_back_with_the_reason_and_the_fixed_one_runs():
    seen: list[str] = []
    cyclic = plan_of(("a", ["b"]), ("b", ["a"]))
    good = plan_of(("a", []))
    with (
        planner_agent.override(model=planner([cyclic, good], seen)),
        executor_agent.override(model=Executors().model),
        synthesizer_agent.override(model=synthesizer([])),
    ):
        result = await run_planner_executor(QUESTION)

    assert [s.id for s in result.output.plan.steps] == ["a"]
    assert "wait on each other" in seen[1]  # the second request carried the planner's mistake
    assert [s.agent for s in result.steps].count("planner_executor.planner") == 1  # one planner run


# --- Running the plan ---


async def test_independent_steps_run_together_and_the_step_that_needs_them_runs_after():
    executors = Executors()
    plan = plan_of(("s1", []), ("s2", []), ("s3", []), ("s4", ["s1", "s2", "s3"]))
    result, seen = await run([plan], executors)
    output = result.output

    assert output.waves == [["s1", "s2", "s3"], ["s4"]]
    assert executors.peak == 3  # the three lookups really overlapped
    assert output.failed == [] and output.skipped == []
    assert set(output.results) == {"s1", "s2", "s3", "s4"}
    assert [s.agent for s in result.steps][0] == "planner_executor.planner"
    assert [s.agent for s in result.steps][-1] == "planner_executor.synthesizer"
    assert len(result.steps) == 6  # planner, four executors, synthesizer


async def test_a_step_sees_its_own_instruction_and_only_the_results_it_depends_on():
    executors = Executors()
    plan = plan_of(("s1", []), ("s2", []), ("s3", ["s1"]), ("s4", ["s2", "s3"]))
    await run([plan], executors)

    assert "do s1" in executors.prompts["s1"] and "(none)" in executors.prompts["s1"]
    assert "result of s2" not in executors.prompts["s1"]  # a sibling's result is not shared
    assert "result of s1" in executors.prompts["s3"]  # its dependency's is
    assert "result of s2" not in executors.prompts["s3"]  # a step it does not depend on is not
    assert QUESTION in executors.prompts["s3"]  # the question is given for context
    assert "result of s2" in executors.prompts["s4"] and "result of s3" in executors.prompts["s4"]
    assert "result of s1" not in executors.prompts["s4"]  # only what it named, not what is upstream


async def test_a_chain_of_steps_runs_one_wave_at_a_time():
    executors = Executors()
    result, _ = await run([plan_of(("s1", []), ("s2", ["s1"]), ("s3", ["s2"]))], executors)
    assert result.output.waves == [["s1"], ["s2"], ["s3"]]
    assert executors.peak == 1


async def test_executors_use_the_real_tool_and_the_ledger_records_it():
    deps = PlanDeps()
    executors = Executors(lookups={"s1": "Quillhaven", "s2": "Tarnby"})
    result, _ = await run([plan_of(("s1", []), ("s2", []), ("s3", ["s1", "s2"]))], executors, deps)

    assert sorted(deps.calls) == ["Quillhaven", "Tarnby"]
    returns = [
        p.content
        for m in result.all_messages()
        for p in m.parts
        if isinstance(p, ToolReturnPart) and p.tool_name == "get_city"
    ]
    assert {r["name"] for r in returns} == {"Quillhaven", "Tarnby"}


async def test_the_synthesizer_is_given_the_question_and_every_step_result():
    result, seen = await run([plan_of(("s1", []), ("s2", ["s1"]))], Executors())
    assert QUESTION in seen[0]
    assert "result of s1" in seen[0] and "result of s2" in seen[0]
    assert (result.output.result, result.output.subject, result.output.value) == (
        "the answer",
        "Quillhaven",
        1200.0,
    )


async def test_one_budget_covers_every_agent_in_the_run():
    result, _ = await run([plan_of(("s1", []), ("s2", []), ("s3", ["s1", "s2"]))], Executors())
    assert result.usage.requests == 5  # planner + three executors + synthesizer


def test_a_steps_prompt_says_so_when_it_depends_on_nothing():
    step = PlanStep(id="s1", instruction="look it up")
    text = step_prompt("the question", step, {})
    assert "the question" in text and "look it up" in text and "(none)" in text


# --- When a step fails ---


async def test_a_failed_step_skips_what_needed_it_and_nothing_else():
    executors = Executors(fail_on={"s2"})
    plan = plan_of(
        ("s1", []),
        ("s2", []),
        ("s3", []),
        ("s4", ["s2", "s3"]),
        ("s5", ["s4"]),
        ("s6", ["s5", "s1"]),
    )
    result, seen = await run([plan], executors)
    output = result.output

    assert output.failed == ["s2"]
    assert output.skipped == ["s4", "s5", "s6"]  # s5 only needed s4, which was skipped: it cascades
    assert set(output.results) == {"s1", "s3"}  # the siblings of the failed step still ran
    assert output.waves == [["s1", "s2", "s3"]]
    assert set(executors.prompts) == {"s1", "s2", "s3"}  # s4, s5 and s6 never reached an executor
    # The synthesizer is told what did not happen, step by step, rather than left to guess.
    assert "Step s2 (do s2): FAILED" in seen[0]
    assert all(f"Step {s} (do {s}): SKIPPED" in seen[0] for s in ("s4", "s5", "s6"))
    assert "result of s2" not in seen[0]


async def test_a_failure_with_a_long_chain_behind_it_skips_the_whole_chain_and_ends():
    """No wave is left to run when the chain is skipped, so the skipping itself must reach its end."""
    executors = Executors(fail_on={"s1"})
    plan = plan_of(("s0", []), ("s1", []), ("s2", ["s1"]), ("s3", ["s2"]), ("s4", ["s3", "s0"]))
    result, _ = await run([plan], executors)

    assert result.output.failed == ["s1"]
    assert result.output.skipped == ["s2", "s3", "s4"]
    assert result.output.waves == [["s0", "s1"]]


async def test_when_no_step_completes_there_is_nothing_to_answer_from():
    def must_not_run(messages, info):
        raise AssertionError("the synthesizer ran with nothing to go on")

    with (
        planner_agent.override(model=planner([plan_of(("s1", []), ("s2", ["s1"]))])),
        executor_agent.override(model=Executors(fail_on={"s1"}).model),
        synthesizer_agent.override(model=FunctionModel(must_not_run)),
        pytest.raises(AllStepsFailedError),
    ):
        await run_planner_executor(QUESTION)


async def test_running_out_of_budget_ends_the_run_instead_of_being_a_failed_step():
    def over_budget(messages, info):
        raise UsageLimitExceeded("the request limit was reached")

    with (
        planner_agent.override(
            model=planner([plan_of(("s1", []), ("s2", []), ("s3", ["s1", "s2"]))])
        ),
        executor_agent.override(model=FunctionModel(over_budget)),
        synthesizer_agent.override(model=synthesizer([])),
        pytest.raises(UsageLimitExceeded),
    ):
        await run_planner_executor(QUESTION)


async def test_cancellation_is_not_mistaken_for_a_failed_step():
    async def cancelled(messages, info: AgentInfo) -> ModelResponse:
        raise asyncio.CancelledError

    with (
        planner_agent.override(model=planner([plan_of(("s1", []))])),
        executor_agent.override(model=FunctionModel(cancelled)),
        synthesizer_agent.override(model=synthesizer([])),
        pytest.raises(asyncio.CancelledError),
    ):
        await run_planner_executor(QUESTION)
