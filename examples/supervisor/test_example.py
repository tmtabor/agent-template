"""The supervisor delegates to real workers, passes their results along, and shares one budget."""

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import UsageLimits

from examples.supervisor import agent as supervisor
from examples.supervisor.agent import (
    analyst_agent,
    run_supervisor,
    supervisor_agent,
    writer_agent,
)


def prompt_of(messages) -> str:
    return "\n".join(
        str(p.content) for m in messages for p in m.parts if isinstance(p, UserPromptPart)
    )


def final(info: AgentInfo, fields: dict) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, fields)])


def worker(fields: dict, seen: list[str] | None = None):
    """A worker that records the prompt it was given and returns `fields`."""

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(prompt_of(messages))
        return final(info, fields)

    return FunctionModel(model_fn)


def supervisor_that(*plan: tuple[str, str] | dict):
    """A supervisor that makes the delegation calls in `plan`, then returns the final dict."""
    remaining = list(plan)

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        step = remaining.pop(0)
        if isinstance(step, dict):
            return final(info, step)
        tool, task = step
        return ModelResponse(parts=[ToolCallPart(tool, {"task": task})])

    return FunctionModel(model_fn)


def tool_outputs(result) -> dict[str, str]:
    return {
        p.tool_name: str(p.content)
        for m in result.all_messages()
        for p in m.parts
        if isinstance(p, ToolReturnPart) and p.tool_name != "final_result"
    }


async def test_research_then_write_hands_the_findings_to_the_writer():
    writer_saw: list[str] = []
    plan = supervisor_that(
        ("delegate_to_analyst", "monorepos"),
        ("delegate_to_writer", "Write one sentence from: - one repo\n- shared tooling"),
        {"result": "Monorepos share tooling.", "steps_taken": ["analyst", "writer"]},
    )
    with (
        supervisor_agent.override(model=plan),
        analyst_agent.override(model=worker({"points": ["one repo", "shared tooling"]})),
        writer_agent.override(model=worker({"text": "Monorepos share tooling."}, writer_saw)),
    ):
        result = await run_supervisor("Explain monorepos")

    assert result.output.steps_taken == ["analyst", "writer"]
    outputs = tool_outputs(result)
    assert outputs["delegate_to_analyst"] == "- one repo\n- shared tooling"  # one point per line
    assert outputs["delegate_to_writer"] == "Monorepos share tooling."
    assert "shared tooling" in writer_saw[0]  # the supervisor passed the findings on


async def test_the_supervisor_may_call_just_one_worker():
    plan = supervisor_that(
        ("delegate_to_writer", "Say hello"),
        {"result": "Hello", "steps_taken": ["writer"]},
    )
    with (
        supervisor_agent.override(model=plan),
        writer_agent.override(model=worker({"text": "Hello"})),
    ):
        result = await run_supervisor("Say hello")
    assert set(tool_outputs(result)) == {"delegate_to_writer"}


async def test_the_result_has_one_step_and_the_workers_spend_is_in_the_total():
    plan = supervisor_that(
        ("delegate_to_analyst", "x"), {"result": "r", "steps_taken": ["analyst"]}
    )
    with (
        supervisor_agent.override(model=plan),
        analyst_agent.override(model=worker({"points": ["p"]})),
    ):
        result = await run_supervisor("x")

    assert [step.agent for step in result.steps] == ["supervisor"]
    # Two supervisor requests (the delegation, then the answer) plus the analyst's one.
    assert result.usage.requests == 3


async def test_the_workers_share_the_supervisors_budget(monkeypatch):
    """request_limit=2 allows the supervisor's two requests but not the worker's third."""
    monkeypatch.setattr(supervisor, "USAGE_LIMITS", UsageLimits(request_limit=2))
    plan = supervisor_that(
        ("delegate_to_analyst", "x"), {"result": "r", "steps_taken": ["analyst"]}
    )
    with (
        supervisor_agent.override(model=plan),
        analyst_agent.override(model=worker({"points": ["p"]})),
        pytest.raises(UsageLimitExceeded),
    ):
        await run_supervisor("x")
