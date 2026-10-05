"""Run an example against a real model, check it, and describe what happened.

Shared by `scripts/record_example.py` (writes sample_run.md) and `scripts/release_check.py`
(verifies every example before a release). Everything here works from a `RunResult`, so it is
tested offline with `TestModel` — the real model is only involved at the single `run(...)` call.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from agent.runs import RunResult, Step
from example_manifest import Example

MAX_FIELD_CHARS = 500  # long prompts, tool arguments and results are clipped in transcripts
OUTPUT_TOOL = "final_result"  # Pydantic AI's default name for the structured-output "tool"


@dataclass
class LiveRun:
    """One real run of an example's `run` helper."""

    example: Example
    result: RunResult
    model: str
    duration_s: float
    recorded_on: date

    @property
    def tokens(self) -> int:
        return (self.result.usage.input_tokens or 0) + (self.result.usage.output_tokens or 0)

    @property
    def cost(self) -> Decimal | None:
        """Total cost, or None when the model can't be priced (e.g. a local Ollama model)."""
        costs = [step_cost(step) for step in self.result.steps]
        if not costs or any(c is None for c in costs):
            return None
        return sum(costs, Decimal(0))


async def run_live(
    example: Example,
    run: Callable[[str], Awaitable[RunResult]],
    model: str,
) -> LiveRun:
    """Call the example's run helper with its smoke input and time it."""
    started = time.perf_counter()
    result = await run(example.smoke_input)
    return LiveRun(
        example=example,
        result=result,
        model=model,
        duration_s=time.perf_counter() - started,
        recorded_on=datetime.now(UTC).date(),
    )


# --- Usage per step ---------------------------------------------------------------------


def responses(step: Step) -> list[ModelResponse]:
    return [m for m in step.result.all_messages() if isinstance(m, ModelResponse)]


def step_tokens(step: Step) -> int:
    # Per-response usage, because every step shares one cumulative RunUsage (see agent/runs.py).
    return sum((r.usage.input_tokens or 0) + (r.usage.output_tokens or 0) for r in responses(step))


def step_cost(step: Step) -> Decimal | None:
    try:
        return sum((Decimal(str(r.cost().total_price)) for r in responses(step)), Decimal(0))
    except LookupError:  # Pydantic AI has no price for this provider/model
        return None


def tools_called(result: RunResult) -> set[str]:
    """Names of the tools whose results appear anywhere in the run (the output tool excluded)."""
    return {
        part.tool_name
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name != OUTPUT_TOOL
    }


# --- Verification -----------------------------------------------------------------------


def verify(live: LiveRun) -> list[str]:
    """What is wrong with this run, in plain English. Empty means it passed.

    A run that raised never gets here; the caller records that as a failure with the error.
    """
    example, result = live.example, live.result
    failures: list[str] = []
    if not isinstance(result, RunResult):
        return [f"{example.run} returned {type(result).__name__}, not a RunResult"]
    if result.output is None:
        failures.append("the run's output is None")
    if not result.steps:
        failures.append("the run recorded no steps")
    for step in result.steps:
        name = example.name
        if step.agent != name and not step.agent.startswith(f"{name}."):
            failures.append(f"step label {step.agent!r} is not labeled for the example")
    missing = set(example.expected_tools) - tools_called(result)
    if missing:
        failures.append(f"the model never called the expected tool(s): {sorted(missing)}")
    if live.cost is not None and live.cost > Decimal(str(example.cost_budget_usd)):
        failures.append(f"cost ${live.cost:.4f} exceeds the ${example.cost_budget_usd:.2f} budget")
    return failures


# --- Transcript -------------------------------------------------------------------------


def clip(text: str, limit: int = MAX_FIELD_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def as_text(value: Any) -> str:
    """A compact one-line rendering of a tool argument or result."""
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    if isinstance(value, str):
        return " ".join(value.split())
    return json.dumps(value, default=str)


def quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def fenced(output: Any) -> str:
    if isinstance(output, BaseModel):
        return f"```json\n{output.model_dump_json(indent=2)}\n```"
    return f"```text\n{output}\n```"


def money(cost: Decimal | None) -> str:
    return f"${cost:.4f}" if cost is not None else "cost unknown"


def render_step(index: int, step: Step) -> str:
    output = step.result.output
    messages = step.result.all_messages()
    prompt = next(
        (
            str(part.content)
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart)
        ),
        "",
    )
    lines = [
        f"### {index}. `{step.agent}`",
        f"*{step_tokens(step):,} tokens · {money(step_cost(step))}*",
        "",
        "**Prompt**",
        quote(clip(prompt)),
        "",
    ]

    events: list[str] = []
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart) and part.tool_name != OUTPUT_TOOL:
                events.append(f"called `{part.tool_name}({clip(as_text(part.args), 200)})`")
            elif isinstance(part, ToolReturnPart) and part.tool_name != OUTPUT_TOOL:
                events.append(f"`{part.tool_name}` returned: {clip(as_text(part.content), 200)}")
            elif isinstance(part, RetryPromptPart):
                events.append(f"asked to retry: {clip(as_text(part.content), 200)}")
            elif isinstance(part, TextPart) and part.content.strip() != str(output).strip():
                events.append(f"said: {clip(as_text(part.content), 200)}")
    if events:
        lines += ["**What happened**", *(f"- {event}" for event in events), ""]

    lines += ["**Output**", fenced(output), ""]
    return "\n".join(lines)


def render_transcript(live: LiveRun) -> str:
    """The sample_run.md for this run: input, every step, and the result."""
    example, result = live.example, live.result
    n = len(result.steps)
    summary = (
        f"Recorded {live.recorded_on.isoformat()} with `{live.model}` · "
        f"{n} step{'s' if n != 1 else ''} · {live.tokens:,} tokens · {money(live.cost)} · "
        f"{live.duration_s:.1f} s"
    )
    parts = [
        f"# Sample run: {example.title}",
        "",
        f"*{summary}.*",
        f"*Model output varies between runs. Regenerate with "
        f"`uv run python scripts/record_example.py {example.name}`.*",
        "",
        "## Input",
        "",
        quote(example.smoke_input),
        "",
        "## Steps",
        "",
        *(render_step(i, step) for i, step in enumerate(result.steps, 1)),
        "## Result",
        "",
        f"`{example.run}(...).output`",
        "",
        fenced(result.output),
        "",
    ]
    return "\n".join(parts)
