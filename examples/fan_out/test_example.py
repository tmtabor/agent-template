"""Workers run in parallel, one failure is tolerated, and total failure is reported."""

import asyncio

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from examples.fan_out.agent import (
    PERSPECTIVES,
    AllWorkersFailedError,
    aggregator_agent,
    run_fan_out,
    worker_agent,
)


def prompt_of(messages) -> str:
    return "\n".join(str(p.content) for p in messages[-1].parts if isinstance(p, UserPromptPart))


def summarizer(seen: list[str]):
    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        seen.append(prompt_of(messages))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"result": "summary"})])

    return FunctionModel(model_fn)


def workers(fail_on: set[str] = frozenset(), stats: dict | None = None):
    """Each worker answers `finding about <perspective>`, or raises if told to fail."""

    async def model_fn(messages, info: AgentInfo) -> ModelResponse:
        perspective = next(p for p in PERSPECTIVES if f"Perspective: {p}" in prompt_of(messages))
        if stats is not None:
            stats["running"] += 1
            stats["peak"] = max(stats["peak"], stats["running"])
            await asyncio.sleep(0.01)  # yield so the other workers can start
            stats["running"] -= 1
        if perspective in fail_on:
            raise RuntimeError(f"{perspective} worker is down")
        fields = {"result": f"finding about {perspective}"}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, fields)])

    return FunctionModel(model_fn)


async def test_every_perspective_is_analyzed_and_summarized():
    seen: list[str] = []
    with worker_agent.override(model=workers()), aggregator_agent.override(model=summarizer(seen)):
        output = await run_fan_out("a topic")

    assert output.result == "summary"
    assert output.perspectives_used == PERSPECTIVES
    assert output.perspectives_failed == []
    assert all(f"finding about {p}" in seen[0] for p in PERSPECTIVES)


async def test_the_workers_really_run_at_the_same_time():
    stats = {"running": 0, "peak": 0}
    with (
        worker_agent.override(model=workers(stats=stats)),
        aggregator_agent.override(model=summarizer([])),
    ):
        await run_fan_out("a topic")
    assert stats["peak"] == len(PERSPECTIVES)


async def test_a_failed_worker_is_reported_and_the_rest_still_count():
    seen: list[str] = []
    with (
        worker_agent.override(model=workers(fail_on={"risks"})),
        aggregator_agent.override(model=summarizer(seen)),
    ):
        output = await run_fan_out("a topic")

    assert output.perspectives_failed == ["risks"]
    assert output.perspectives_used == ["benefits", "drawbacks"]
    assert "finding about risks" not in seen[0]


async def test_when_every_worker_fails_nothing_is_summarized():
    def must_not_run(messages, info):
        raise AssertionError("the aggregator ran with no findings")

    with (
        worker_agent.override(model=workers(fail_on=set(PERSPECTIVES))),
        aggregator_agent.override(model=FunctionModel(must_not_run)),
        pytest.raises(AllWorkersFailedError),
    ):
        await run_fan_out("a topic")
