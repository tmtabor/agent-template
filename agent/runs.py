"""What every `run_*` helper returns: the output plus the evidence of how it was produced.

A run helper used to return only the validated output and throw away what Pydantic AI had
already computed — usage, messages, per-step detail. `RunResult` keeps it, uniformly: a
single agent is a one-step run, a router or pipeline a several-step run, and callers always
write `(await run_x(...)).output`. Moving an agent from one shape to the other never changes
a call site.

    result = await run_router("I was charged twice")
    result.output        # the run's own output (for flows, built in code from the steps)
    result.usage         # total usage across every step
    result.steps         # [Step(agent="router.classifier", result=<AgentRunResult>), ...]
    result.steps[0].result   # the native Pydantic AI result, untouched

`Flow` builds a `RunResult`: it owns the shared usage and limits, runs agents through them,
and records each step. Use it in your own run helpers; `examples/` shows the shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RunUsage, UsageLimits


@dataclass
class Step:
    """One agent run within a flow."""

    agent: str  # the agent's label (its `name`, see agent_label in agent/logging.py)
    result: AgentRunResult[Any]  # the native Pydantic AI result, untouched


@dataclass
class RunResult[OutputT]:
    """The output of a run helper, with every step that produced it."""

    output: OutputT
    steps: list[Step]
    # One RunUsage shared by every step, so this is the total. It is stored rather than
    # summed from the steps, which all point at the same object and would be counted twice.
    usage: RunUsage = field(default_factory=RunUsage)

    def all_messages(self) -> list[ModelMessage]:
        """Every step's messages, in step order."""
        return [message for step in self.steps for message in step.result.all_messages()]


class Flow:
    """Runs agents against one shared budget and records each as a step.

        flow = Flow(USAGE_LIMITS)
        classified = await flow.run(classifier, user_input, deps=deps)
        answered = await flow.run(specialist, user_input, deps=deps)
        return flow.finish(RouterOutput(...))

    `limits` bounds the whole flow, not each call: every run draws on the same `RunUsage`.
    Steps are recorded as they complete, so parallel steps (asyncio.gather) appear in
    completion order. A run that raises records nothing.
    """

    def __init__(self, limits: UsageLimits) -> None:
        self.limits = limits
        self.usage = RunUsage()
        self.steps: list[Step] = []

    async def run[DepsT, OutT](
        self, agent: Agent[DepsT, OutT], prompt: str, *, deps: DepsT, **kwargs: Any
    ) -> AgentRunResult[OutT]:
        """Run `agent` on `prompt` within this flow's budget and record the step."""
        result = await agent.run(
            prompt, deps=deps, usage=self.usage, usage_limits=self.limits, **kwargs
        )
        self.steps.append(Step(agent=agent.name or "agent", result=result))
        return result

    def finish[OutputT](self, output: OutputT) -> RunResult[OutputT]:
        """Close the flow with its output."""
        return RunResult(output=output, steps=list(self.steps), usage=self.usage)
