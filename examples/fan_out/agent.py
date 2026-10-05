"""Fan-out / fan-in: run workers in parallel, then combine their results.

Use this pattern when:
- Independent subtasks can run at the same time (different perspectives, sources, chunks)
- Wall-clock time matters, or one worker's failure shouldn't sink the whole answer
- A final step must reconcile what the workers produced

    topic ─┬→ worker (pros)  ─┐
           ├→ worker (cons)  ─┼→ aggregator → answer
           └→ worker (risks) ─┘

The fan-out is `asyncio.gather` — ordinary Python, not an LLM decision.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.usage import RunUsage, UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# Parallel runs all draw on one shared RunUsage, so this bounds the whole fan-out. Size
# request_limit for (workers + aggregator), with headroom for retries.
USAGE_LIMITS = UsageLimits(
    request_limit=20, total_tokens_limit=200_000, cost_limit=settings.cost_limit
)

PERSPECTIVES = ["benefits", "drawbacks", "risks"]


@dataclass
class FanOutDeps:
    """Runtime dependencies shared by the workers and the aggregator."""

    pass


class Finding(BaseModel):
    result: str


worker_agent: Agent[FanOutDeps, Finding] = Agent(
    settings.model,
    name=f"{LABEL}.worker",
    output_type=Finding,
    deps_type=FanOutDeps,
    capabilities=[RaiseContentFilterError()],
    instructions="You analyze a topic from one given perspective, in two or three sentences.",
)


class FanOutOutput(BaseModel):
    result: str
    perspectives_used: list[str]
    perspectives_failed: list[str]


class Summary(BaseModel):
    result: str


aggregator_agent: Agent[FanOutDeps, Summary] = Agent(
    settings.model,
    name=f"{LABEL}.aggregator",
    output_type=Summary,
    deps_type=FanOutDeps,
    capabilities=[RaiseContentFilterError()],
    instructions=(
        "You are given findings on one topic from several perspectives. Combine them into one "
        "balanced summary. Do not mention perspectives that were not provided."
    ),
)


class AllWorkersFailedError(Exception):
    """Every parallel worker failed, so there is nothing to aggregate."""


async def run_fan_out(user_input: str, deps: FanOutDeps | None = None) -> FanOutOutput:
    """Analyze `user_input` from several perspectives in parallel, then summarize.

    One failing worker is tolerated — the summary is built from the rest and the failure is
    reported in `perspectives_failed`. If every worker fails there is nothing to summarize.

    Raises:
        AllWorkersFailedError: When no worker produced a finding.
    """
    if deps is None:
        deps = FanOutDeps()
    usage = RunUsage()  # shared across the parallel runs, so USAGE_LIMITS bounds all of them

    # return_exceptions=True keeps one failure from cancelling its siblings and discarding
    # work already paid for.
    outcomes = await asyncio.gather(
        *(
            worker_agent.run(
                f"Perspective: {perspective}\nTopic: {user_input}",
                deps=deps,
                usage=usage,
                usage_limits=USAGE_LIMITS,
            )
            for perspective in PERSPECTIVES
        ),
        return_exceptions=True,
    )

    findings: dict[str, str] = {}
    failed: list[str] = []
    for perspective, outcome in zip(PERSPECTIVES, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            # Let cancellation and Ctrl-C through; only treat ordinary failures as "a worker failed".
            if not isinstance(outcome, Exception):
                raise outcome
            logger.warning(
                "Worker failed", extra={"perspective": perspective, "error": str(outcome)}
            )
            failed.append(perspective)
        else:
            findings[perspective] = outcome.output.result

    if not findings:
        raise AllWorkersFailedError(f"All {len(PERSPECTIVES)} workers failed for: {user_input!r}")

    material = "\n\n".join(f"{name}:\n{text}" for name, text in findings.items())
    summary = await aggregator_agent.run(
        f"Topic: {user_input}\n\n{material}",
        deps=deps,
        usage=usage,
        usage_limits=USAGE_LIMITS,
    )
    return FanOutOutput(
        result=summary.output.result,
        perspectives_used=list(findings),
        perspectives_failed=failed,
    )


if __name__ == "__main__":
    configure_logging()
    print(asyncio.run(run_fan_out("Adopting a monorepo")))
