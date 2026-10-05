"""Observe what a run actually did, from its OpenTelemetry spans.

A `RunResult` shows the steps a flow recorded, but not everything that ran: a supervisor's
workers run inside a tool call, so they are in no step. The spans see every agent run and tool
call. `traced_run` runs a helper and returns both, using the same span capture that the span-based
evaluators (`MaxToolCalls`, `ToolCorrectness`, …) use, so it needs the Logfire setup that
`configure_logging()` performs (evals/conftest.py and tests/conftest.py both do).

    traced = await traced_run(run_supervisor, "Research X, then write Y")
    traced.result.output                 # what the helper returned
    traced.agents_ran                    # {"supervisor", "supervisor.analyst", "supervisor.writer"}
    traced.tools_called                  # ["delegate_to_analyst", "delegate_to_writer"]
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.otel import SpanTree

from agent.runs import RunResult

AGENT_SPAN = "invoke_agent"  # Pydantic AI's span for one agent run
TOOL_SPAN = "execute_tool"  # …and for one tool call
AGENT_NAME = "gen_ai.agent.name"
TOOL_NAME = "gen_ai.tool.name"
OUTPUT_TOOL = "final_result"  # the structured-output "tool"; not a tool the agent chose to call


@dataclass
class Traced:
    """A run helper's result, plus what its spans show ran."""

    result: RunResult
    agents_ran: set[str]  # the name of every agent that ran, including workers inside tools
    tools_called: list[str]  # every tool call, in order (the output tool excluded)


class _Capture(Evaluator[str, str]):
    """Stashes the span tree: pydantic-evals only hands it to evaluators."""

    def __init__(self, holder: dict[str, Any]) -> None:
        self.holder = holder

    def evaluate(self, ctx: EvaluatorContext[str, str]) -> bool:
        self.holder["tree"] = ctx.span_tree
        return True


def read_spans(tree: SpanTree) -> tuple[set[str], list[str]]:
    """The agent names and tool-call names found in a span tree."""
    agents = {
        node.attributes[AGENT_NAME]
        for node in tree.find(lambda n: n.name.startswith(AGENT_SPAN))
        if AGENT_NAME in node.attributes
    }
    tools = [
        node.attributes[TOOL_NAME]
        for node in tree.find(lambda n: n.name.startswith(TOOL_SPAN))
        if node.attributes.get(TOOL_NAME) not in (None, OUTPUT_TOOL)
    ]
    return agents, tools


async def traced_run(run: Callable[[str], Awaitable[RunResult]], user_input: str) -> Traced:
    """Run `run(user_input)` while recording its spans. Exceptions from the run propagate."""
    holder: dict[str, Any] = {}

    async def task(text: str) -> str:
        try:
            holder["result"] = await run(text)
        except Exception as exc:  # pydantic-evals would swallow it into the report
            holder["error"] = exc
            raise
        return str(holder["result"].output)

    dataset = Dataset(
        name="traced_run",
        cases=[Case(name="run", inputs=user_input)],
        evaluators=[_Capture(holder)],
    )
    await dataset.evaluate(task, progress=False)

    if "error" in holder:
        raise holder["error"]
    tree = holder.get("tree")
    if not isinstance(tree, SpanTree):
        raise RuntimeError(
            "no span tree was recorded: call configure_logging() before tracing a run "
            f"(got {tree!r})"
        )
    agents, tools = read_spans(tree)
    return Traced(result=holder["result"], agents_ran=agents, tools_called=tools)
