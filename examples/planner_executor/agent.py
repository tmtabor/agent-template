"""Planner-executor: one agent writes the whole plan, then code carries it out.

Use this pattern when:
- A question needs several different pieces of work, and what they are depends on the question
- Some of those pieces are independent (so they can run at the same time) and some need others' results
- You want the plan to exist as data you can check, log, show or approve *before* anything runs

How it works:

    question → planner → Plan(steps) → check it in code → executors, a wave at a time → synthesizer
                                         (ids, dependencies, no cycles)   (independent steps in parallel)

The planner never answers and never calls a tool: it only writes a `Plan`, a list of steps that each
say what to do and which earlier steps they need. Code validates the plan (a bad one is sent back to
the planner to fix), then runs it: every step whose dependencies are done runs now, all of those in
parallel, and each executor sees only its own step and the results it depends on. A step that fails
takes down only the steps that needed it. A last agent writes the answer from whatever completed.

Compare `supervisor`, where the model decides what to delegate one turn at a time and nothing is
known in advance, and `pipeline` / `fan_out`, where the shape is fixed in code. Here the *model*
chooses the shape, once, up front, and *code* holds it to the rules.

The cities are invented, so a model cannot know them and must use the tool. Replace `get_city` and
the executor's instructions with your own tools; the planner, the checking and the scheduling stay.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext, ToolFailed
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.prompts.templates import load_prompt
from agent.runs import Flow, RunResult

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

MAX_STEPS = 6  # the most steps a plan may have (the planner is told, and the check enforces it)

# One budget for the whole run: the planner, every executor and the synthesizer share it. Sized for
# a plan of MAX_STEPS steps that each use the tool, with headroom for retries.
USAGE_LIMITS = UsageLimits(
    request_limit=40, total_tokens_limit=200_000, cost_limit=settings.cost_limit
)


# --- The data ---
@dataclass(frozen=True)
class City:
    name: str
    population: int
    area_km2: float
    founded: int


CITIES = {
    city.name: city
    for city in (
        City("Brindlemoor", 84_000, 120.0, 1721),
        City("Quillhaven", 156_000, 130.0, 1648),
        City("Tarnby", 39_000, 130.0, 1893),
        City("Ashwick", 210_000, 350.0, 1502),
    )
}


def density(city: City) -> float:
    """People per km², which is what the example's questions are about."""
    return round(city.population / city.area_km2, 1)


@dataclass
class PlanDeps:
    """Runtime dependencies shared by every agent in the run."""

    cities: dict[str, City] = field(default_factory=lambda: dict(CITIES))
    # Every city name the executors asked the tool about, in order: the evidence of what ran.
    calls: list[str] = field(default_factory=list)


# --- The plan ---
class PlanStep(BaseModel):
    id: str = Field(description="A short unique name for the step, such as 's1'.")
    instruction: str = Field(description="What this one step must do, able to be done on its own.")
    depends_on: list[str] = Field(
        default_factory=list, description="Ids of the steps whose results this step needs."
    )


class Plan(BaseModel):
    steps: list[PlanStep]


class PlanError(ValueError):
    """The plan breaks a rule. The message says which, so the planner can fix it."""


def check_plan(plan: Plan) -> None:
    """Raise PlanError unless the plan is one that can be carried out.

    A plan has between 1 and MAX_STEPS steps, unique ids, dependencies that name other steps in the
    plan, no cycles (a step cannot, even indirectly, wait for itself), and **one final step**: the
    only step nothing else depends on, so every other step feeds into it. That last rule is how a
    step that uses another's result but forgot to say so is caught. A planner that writes
    "look up A", "look up B" and "compare them" with the third step's `depends_on` left empty
    leaves three loose ends, and the check names them.
    """
    if not 1 <= len(plan.steps) <= MAX_STEPS:
        raise PlanError(f"a plan needs between 1 and {MAX_STEPS} steps, not {len(plan.steps)}")
    ids = [step.id for step in plan.steps]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise PlanError(f"step ids must be unique; repeated: {duplicates}")
    for step in plan.steps:
        unknown = [d for d in step.depends_on if d not in ids]
        if unknown:
            raise PlanError(
                f"step {step.id!r} depends on {unknown}, which are not steps in the plan"
            )
        if step.id in step.depends_on:
            raise PlanError(f"step {step.id!r} depends on itself")
    # Peel off steps whose dependencies are all done; if some remain, they wait on each other.
    done: set[str] = set()
    remaining = list(plan.steps)
    while remaining:
        runnable = [s for s in remaining if set(s.depends_on) <= done]
        if not runnable:
            raise PlanError(
                f"the steps {sorted(s.id for s in remaining)} wait on each other (a cycle)"
            )
        done |= {s.id for s in runnable}
        remaining = [s for s in remaining if s.id not in done]
    needed = {dep for step in plan.steps for dep in step.depends_on}
    loose_ends = [step.id for step in plan.steps if step.id not in needed]
    if len(loose_ends) > 1:
        # Say what to change, not only what is wrong: the last loose end is the likeliest final step.
        *others, final = loose_ends
        raise PlanError(
            f"the steps {loose_ends} are not used by any other step, so the plan has no single "
            "final step that answers the question. A step that uses another step's result must "
            f"list it in depends_on. For example, make {final!r} the final step by setting its "
            f"depends_on to include {others}"
        )


# --- Agents ---
planner_agent: Agent[PlanDeps, Plan] = Agent(
    settings.model,
    name=f"{LABEL}.planner",
    output_type=Plan,
    deps_type=PlanDeps,
    capabilities=[RaiseContentFilterError()],
    instructions=load_prompt("planner_executor_planner"),
    retries={"output": 3},  # how many times a rejected plan may be sent back to be rewritten
)


@planner_agent.output_validator
def the_plan_must_be_carryable(plan: Plan) -> Plan:
    try:
        check_plan(plan)
    except PlanError as exc:
        raise ModelRetry(f"The plan is not valid: {exc}. Write the whole plan again.") from exc
    return plan


class StepResult(BaseModel):
    result: str


executor_agent: Agent[PlanDeps, StepResult] = Agent(
    settings.model,
    name=f"{LABEL}.executor",
    output_type=StepResult,
    deps_type=PlanDeps,
    capabilities=[RaiseContentFilterError()],
    instructions=load_prompt("planner_executor_executor"),
)


@executor_agent.tool
def get_city(ctx: RunContext[PlanDeps], name: str) -> dict[str, str | int | float]:
    """Look up a city's population, its area in square kilometres, and the year it was founded."""
    ctx.deps.calls.append(name)
    match = next(
        (c for c in ctx.deps.cities.values() if c.name.lower() == name.strip().lower()), None
    )
    if match is None:
        known = ", ".join(sorted(ctx.deps.cities))
        raise ToolFailed(f"There is no city called {name!r}. The cities are: {known}")
    return {
        "name": match.name,
        "population": match.population,
        "area_km2": match.area_km2,
        "founded": match.founded,
    }


class Answer(BaseModel):
    # `result` is the conventional output field in these examples; the generated
    # eval starter reads it when present (see evals/helpers.py).
    result: str
    subject: str | None = None
    value: float | None = None


synthesizer_agent: Agent[PlanDeps, Answer] = Agent(
    settings.model,
    name=f"{LABEL}.synthesizer",
    output_type=Answer,
    deps_type=PlanDeps,
    capabilities=[RaiseContentFilterError()],
    instructions=load_prompt("planner_executor_synthesizer"),
)


# --- The run ---
class PlannerExecutorOutput(BaseModel):
    result: str
    subject: str | None
    value: float | None
    plan: Plan
    results: dict[str, str]  # step id -> what its executor reported, for the steps that completed
    waves: list[list[str]]  # the step ids that ran together, in the order the waves ran
    failed: list[str]  # steps whose executor raised
    skipped: list[str]  # steps never run because a step they needed failed or was skipped


class AllStepsFailedError(Exception):
    """No step of the plan completed, so there is nothing to answer from."""


def step_prompt(question: str, step: PlanStep, results: dict[str, str]) -> str:
    """What one executor is told: the question, its own step, and only the results it depends on."""
    needed = "\n".join(f"- {dep}: {results[dep]}" for dep in step.depends_on) or "(none)"
    return (
        f"Overall question (for context): {question}\n\n"
        f"Your step ({step.id}): {step.instruction}\n\n"
        f"Results of the steps yours depends on:\n{needed}"
    )


def outcome_of(step: PlanStep, results: dict[str, str], failed: list[str]) -> str:
    """How a step ended, for the synthesizer: its result, or why there is none."""
    if step.id in results:
        return results[step.id]
    return "FAILED" if step.id in failed else "SKIPPED (a step it needed did not complete)"


async def run_planner_executor(
    user_input: str, deps: PlanDeps | None = None
) -> RunResult[PlannerExecutorOutput]:
    """Plan an answer to `user_input`, carry the plan out, and write the answer.

    Returns:
        A RunResult: `.output` is the PlannerExecutorOutput; `.steps` holds the planner, then every
        executor that finished (in completion order), then the synthesizer.

    Raises:
        AllStepsFailedError: When no step of the plan completed.
        UsageLimitExceeded: When the run's shared budget runs out (never treated as a failed step).
    """
    if deps is None:
        deps = PlanDeps()
    logger.info("Running planner-executor", extra={"user_input": user_input})
    flow = Flow(USAGE_LIMITS)  # shared by every agent below, so it bounds the whole run

    plan = (await flow.run(planner_agent, user_input, deps=deps)).output

    pending = {step.id: step for step in plan.steps}
    results: dict[str, str] = {}
    waves: list[list[str]] = []
    failed: list[str] = []
    skipped: list[str] = []
    while True:
        # A step that needs a failed or skipped step can never run. Skipping one can doom another.
        doomed = True
        while doomed:
            doomed = [s for s in pending.values() if set(s.depends_on) & set(failed + skipped)]
            for step in doomed:
                skipped.append(step.id)
                del pending[step.id]
        if not pending:
            break
        ready = [s for s in pending.values() if set(s.depends_on) <= set(results)]
        assert ready, "a checked plan always has a step that can run"  # check_plan guarantees it
        waves.append([s.id for s in ready])
        # return_exceptions=True keeps one failing step from cancelling its siblings' paid-for work.
        outcomes = await asyncio.gather(
            *(
                flow.run(executor_agent, step_prompt(user_input, s, results), deps=deps)
                for s in ready
            ),
            return_exceptions=True,
        )
        for step, outcome in zip(ready, outcomes, strict=True):
            del pending[step.id]
            if isinstance(outcome, BaseException):
                # Running out of budget ends the run; it is not one step's failure. Cancellation
                # and Ctrl-C pass through too.
                if isinstance(outcome, UsageLimitExceeded) or not isinstance(outcome, Exception):
                    raise outcome
                logger.warning("Step failed", extra={"step": step.id, "error": str(outcome)})
                failed.append(step.id)
            else:
                results[step.id] = outcome.output.result

    if not results:
        raise AllStepsFailedError(f"No step of the plan completed for: {user_input!r}")

    report = "\n\n".join(
        f"Step {step.id} ({step.instruction}): {outcome_of(step, results, failed)}"
        for step in plan.steps
    )
    answer = (
        await flow.run(synthesizer_agent, f"Question: {user_input}\n\n{report}", deps=deps)
    ).output
    return flow.finish(
        PlannerExecutorOutput(
            result=answer.result,
            subject=answer.subject,
            value=answer.value,
            plan=plan,
            results=results,
            waves=waves,
            failed=failed,
            skipped=skipped,
        )
    )


if __name__ == "__main__":
    configure_logging()
    demo_deps = PlanDeps()
    run = asyncio.run(
        run_planner_executor(
            "Which of Brindlemoor, Quillhaven and Tarnby is the most densely populated, "
            "and what is its density in people per km²?",
            demo_deps,
        )
    )
    print(run.output.result)
    print(f"plan: {[(s.id, s.depends_on) for s in run.output.plan.steps]}")
    print(f"waves: {run.output.waves}")
    print(f"{len(run.steps)} agent runs; cities looked up: {sorted(demo_deps.calls)}")
