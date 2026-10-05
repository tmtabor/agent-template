"""The loop stops when the critic accepts, feeds feedback back in, and is capped."""

from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from examples.evaluator_optimizer.agent import (
    MAX_ITERATIONS,
    critic_agent,
    generator_agent,
    run_evaluator_optimizer,
)


def prompt_of(messages) -> str:
    return "\n".join(str(p.content) for p in messages[-1].parts if isinstance(p, UserPromptPart))


def generator(seen: list[str]):
    """Drafts `draft 1`, `draft 2`, ... and records each prompt."""

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        seen.append(prompt_of(messages))
        fields = {"result": f"draft {len(seen)}"}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, fields)])

    return FunctionModel(model_fn)


def critic(verdicts: list[bool]):
    """Returns the given accept/reject verdicts in order; every rejection carries feedback."""
    remaining = list(verdicts)

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        fields = {"accepted": remaining.pop(0), "feedback": "make it shorter"}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, fields)])

    return FunctionModel(model_fn)


async def test_a_draft_the_critic_accepts_is_returned_after_one_round():
    prompts: list[str] = []
    with (
        generator_agent.override(model=generator(prompts)),
        critic_agent.override(model=critic([True])),
    ):
        result = await run_evaluator_optimizer("a bottle")
        output = result.output

    assert (output.result, output.accepted, output.iterations) == ("draft 1", True, 1)
    assert len(prompts) == 1


async def test_feedback_and_the_previous_draft_go_back_to_the_generator():
    prompts: list[str] = []
    with (
        generator_agent.override(model=generator(prompts)),
        critic_agent.override(model=critic([False, True])),
    ):
        result = await run_evaluator_optimizer("a bottle")
        output = result.output

    assert (output.result, output.accepted, output.iterations) == ("draft 2", True, 2)
    assert "make it shorter" in prompts[1]
    assert [step.agent for step in result.steps] == [
        "evaluator_optimizer.generator",
        "evaluator_optimizer.critic",
        "evaluator_optimizer.generator",
        "evaluator_optimizer.critic",
    ]
    assert "draft 1" in prompts[1]


async def test_a_critic_that_is_never_satisfied_is_capped_not_looped():
    prompts: list[str] = []
    with (
        generator_agent.override(model=generator(prompts)),
        critic_agent.override(model=critic([False] * MAX_ITERATIONS)),
    ):
        result = await run_evaluator_optimizer("a bottle")
        output = result.output

    assert output.accepted is False
    assert output.iterations == MAX_ITERATIONS
    assert output.result == f"draft {MAX_ITERATIONS}"  # the best attempt so far, not an error
