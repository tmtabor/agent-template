"""Tool-calling agent pattern.

Use this pattern when:
- The agent needs to interact with external systems (APIs, databases, files)
- You want the LLM to decide which tools to call and when
- Tool results inform subsequent decisions (agentic loop)

This example answers questions about Python releases by calling a lookup tool. The data
lives in a small in-memory table so it runs anywhere; in a real agent, `ReleaseNotes` is
where an API client or database connection goes.

Key design principles (from production experience):
- Keep tool interfaces simple: fewer optional params = more reliable tool selection
- Translate errors into English: give the LLM enough context to self-correct
- Hold large payloads at the tool layer: don't dump raw API responses into context
- Inject the backend through deps, so tests (and you) can swap it

The tool shows all three error outcomes: success, `ModelRetry` (the model can fix its input),
and `ToolFailed` (expected and terminal — there is nothing to find). See
agent/tools/example.py for the same convention in a standalone tool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext, ToolFailed
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.runs import Flow, RunResult

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# Guardrail against runaway agentic loops. A run that exceeds any limit
# raises UsageLimitExceeded instead of silently burning tokens. Tune per task:
# request_limit caps model round-trips (each tool-call iteration is one
# request), total_tokens_limit caps overall tokens for the run. Set
# AGENT_COST_LIMIT (USD) to add a spend cap — optional, off by default, and only
# useful for models with known pricing (see Settings.cost_limit).
USAGE_LIMITS = UsageLimits(
    request_limit=10, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)


# --- The backend the tool talks to ---
@dataclass(frozen=True)
class Release:
    released: str
    highlights: tuple[str, ...]


# Replace with a real data source. A dict stands in for an API or database here.
RELEASES: dict[str, Release] = {
    "3.11": Release(
        "October 24, 2022",
        (
            "CPython runs about 25% faster on average (the Faster CPython project)",
            "exception groups and except* (PEP 654)",
            "tomllib adds TOML parsing to the standard library (PEP 680)",
        ),
    ),
    "3.12": Release(
        "October 2, 2023",
        (
            "cleaner generics syntax: type parameters and the type statement (PEP 695)",
            "f-strings can nest quotes and span lines (PEP 701)",
            "per-interpreter GIL for subinterpreters (PEP 684)",
        ),
    ),
    "3.13": Release(
        "October 7, 2024",
        (
            "an experimental free-threaded build with the GIL disabled (PEP 703)",
            "an experimental JIT compiler (PEP 744)",
            "a new interactive interpreter with multi-line editing and colour",
        ),
    ),
}


# --- Dependencies ---
@dataclass
class ToolAgentDeps:
    """Runtime dependencies for the tool-calling agent."""

    # The release table the tool reads. Swap in an API client or database in a real agent.
    releases: dict[str, Release] = field(default_factory=lambda: RELEASES)


# --- Output type ---
class ToolAgentOutput(BaseModel):
    # `result` is the conventional output field in these examples; the generated
    # eval starter reads it when present (see evals/helpers.py).
    result: str
    # Pydantic deep-copies mutable defaults, so a plain [] is safe here.
    # Do NOT use dataclasses.field() inside a BaseModel — it is not a
    # Pydantic construct (use pydantic.Field(default_factory=...) if needed).
    versions: list[str] = []


# --- Agent ---
tool_agent: Agent[ToolAgentDeps, ToolAgentOutput] = Agent(
    settings.model,
    name=LABEL,  # labels this agent's run span in Logfire traces
    output_type=ToolAgentOutput,
    deps_type=ToolAgentDeps,
    # Fail fast when the provider filters a response, instead of retrying a
    # refused request or returning partial text.
    capabilities=[RaiseContentFilterError()],
    instructions="""You answer questions about Python releases.

    Use the python_release_notes tool for every fact about a release; do not answer from
    memory. If the tool reports that nothing is available for a version, tell the user that
    plainly and do not guess. In `versions`, list the versions your answer draws on.
    """,
)

VERSION_FORMAT = re.compile(r"\d+\.\d+")


# --- Tools ---
@tool_agent.tool
async def python_release_notes(ctx: RunContext[ToolAgentDeps], version: str) -> str:
    """Look up the release date and headline features of a Python release.

    Args:
        version: A major.minor version such as "3.13". Not "3.13.1" and not "latest".

    Returns:
        The release date and highlights as a short paragraph.

    Raises:
        ModelRetry: When the version isn't in major.minor form, so the model can correct it.
        ToolFailed: When there are no notes for that version (a terminal, expected failure).
    """
    version = version.strip()
    logger.info("Tool called", extra={"tool": "python_release_notes", "version": version})

    if not VERSION_FORMAT.fullmatch(version):
        # The model can fix this by changing its input, so ask it to retry.
        raise ModelRetry(
            f"'{version}' is not a major.minor version like '3.13'. "
            "Call the tool again with just the major and minor numbers."
        )

    release = ctx.deps.releases.get(version)
    if release is None:
        # Nothing exists to find, and retrying won't change that. ToolFailed shows the model
        # the failure without spending retry budget, and tells it what to do instead.
        known = ", ".join(sorted(ctx.deps.releases))
        raise ToolFailed(
            f"There are no release notes for Python {version}. Known versions: {known}. "
            "Tell the user this version is unavailable; do not guess its features."
        )

    highlights = "; ".join(release.highlights)
    return f"Python {version} was released on {release.released}. Highlights: {highlights}."


async def run_tool_agent(
    user_input: str, deps: ToolAgentDeps | None = None
) -> RunResult[ToolAgentOutput]:
    """Run the tool-calling agent.

    Args:
        user_input: The user's message or task description.
        deps: Runtime dependencies. Created with defaults if not provided.

    Returns:
        A RunResult: `.output` is the validated ToolAgentOutput; the tool calls the agent made
        are in `.all_messages()`.
    """
    if deps is None:
        deps = ToolAgentDeps()
    logger.info("Running tool-calling agent", extra={"user_input": user_input})
    flow = Flow(USAGE_LIMITS)
    result = await flow.run(tool_agent, user_input, deps=deps)
    return flow.finish(result.output)


if __name__ == "__main__":
    import asyncio

    configure_logging()
    result = asyncio.run(run_tool_agent("What changed in Python 3.13 compared with 3.12?"))
    print(result.output)
