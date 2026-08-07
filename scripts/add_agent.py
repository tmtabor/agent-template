#!/usr/bin/env python3
"""Scaffold an additional, independent agent alongside the primary one.

Usage:
    uv run python scripts/add_agent.py <name>

Creates agent/agents/<name>.py, agent/prompts/<name>.txt, and
tests/test_agents_<name>.py. Unlike scripts/choose_pattern.py, this never
touches agent/agents/__init__.py — the canonical re-export there
(run_agent, AgentOutput, AgentDeps, agent) stays reserved for the one
primary agent chosen by choose_pattern.py. The new agent is meant to be
imported directly from its own module wherever it's used:

    from agent.agents.<name> import <Name>Deps, <Name>Output, <name>_agent, run_<name>_agent

Use this for apps that need several independent, differently-shaped agents
(e.g. a "newsletter" agent and a "bluesky_post" agent with no shared
identity) — not for a supervisor delegating to workers it controls, which
is still one agent from the outside (see agent/agents/supervisor.py).
"""

import argparse
import keyword
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agent" / "agents"
PROMPTS_DIR = REPO_ROOT / "agent" / "prompts"
TESTS_DIR = REPO_ROOT / "tests"

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Names that would collide with the canonical primary-agent wiring, the
# pattern stubs, or the example tool/prompt files.
RESERVED_NAMES = {
    "single",
    "supervisor",
    "tool_calling",
    "example",
    "agent",
    "agents",
    "run_agent",
    "config",
    "logging",
    "templates",
}

AGENT_MODULE_TEMPLATE = '''"""{Name} agent — an additional, independent agent alongside the app's primary agent.

Scaffolded by `scripts/add_agent.py`. This agent is independent of whichever
pattern (single/supervisor/tool_calling) was chosen for the primary agent —
it is not re-exported from `agent/agents/__init__.py`; import it directly:

    from agent.agents.{name} import {Name}Deps, {Name}Output, {name}_agent, run_{name}_agent

To use:
    1. Define your output type (or use str for unstructured output)
    2. Set your instructions in agent/prompts/{name}.txt
    3. Add tools if needed
    4. Call run_{name}_agent()
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import (  # noqa: F401 — RunContext used in commented tool example below
    Agent,
    RunContext,
)
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import configure_logging, get_logger
from agent.prompts.templates import load_prompt

logger = get_logger(__name__)

# Guardrail against runaway agentic loops. A run that exceeds either limit
# raises UsageLimitExceeded instead of silently burning tokens. Tune per task:
# request_limit caps model round-trips (each tool-call iteration is one
# request), total_tokens_limit caps overall spend.
USAGE_LIMITS = UsageLimits(request_limit=10, total_tokens_limit=100_000)


# --- Output type ---
# Replace with your actual output schema, or use str for unstructured output.
class {Name}Output(BaseModel):
    """Replace with your actual output schema."""

    result: str


# --- Dependencies ---
# Use a dataclass to inject runtime dependencies (DB connections, API clients, etc.)
# Remove if this agent needs no external dependencies.
@dataclass
class {Name}Deps:
    """Runtime dependencies injected into the {name} agent."""

    # example_client: SomeAPIClient  # Add your dependencies here
    pass


# --- Agent definition ---
{name}_agent: Agent[{Name}Deps, {Name}Output] = Agent(
    settings.model,
    name="{name}",  # labels this agent's run span in Logfire traces
    output_type={Name}Output,
    deps_type={Name}Deps,
    instructions=load_prompt("{name}"),  # loads agent/prompts/{name}.txt
)


# --- Tools ---
# Add tools here. See agent/tools/example.py for the full pattern.
# @{name}_agent.tool
# async def my_tool(ctx: RunContext[{Name}Deps], query: str) -> str:
#     """Tool description — this docstring is sent to the LLM."""
#     return "result"


# --- Dynamic instructions (optional) ---
# Use @{name}_agent.instructions for instructions that depend on runtime state.
# @{name}_agent.instructions
# async def dynamic_instructions(ctx: RunContext[{Name}Deps]) -> str:
#     return f"Today is {{date.today()}}."


async def run_{name}_agent(user_input: str, deps: {Name}Deps | None = None) -> {Name}Output:
    """Run the {name} agent with the given user input.

    Args:
        user_input: The user's message or task description.
        deps: Runtime dependencies. Created with defaults if not provided.

    Returns:
        Validated {Name}Output instance.
    """
    if deps is None:
        deps = {Name}Deps()

    logger.info("Running {name} agent", extra={{"user_input": user_input}})

    result = await {name}_agent.run(user_input, deps=deps, usage_limits=USAGE_LIMITS)

    logger.info("{Name} agent run complete", extra={{"output": result.output}})
    return result.output


if __name__ == "__main__":
    import asyncio

    configure_logging()
    output = asyncio.run(run_{name}_agent("Hello, what can you do?"))
    print(output)
'''

PROMPT_TEMPLATE = """You are the {name} agent.

TODO: replace this with real instructions for what the {name} agent should do.
"""

TEST_MODULE_TEMPLATE = '''"""Smoke test for the {name} agent (scaffolded by scripts/add_agent.py).

Imports directly from agent.agents.{name} — additional agents are not
re-exported from agent/agents/__init__.py, unlike the primary agent chosen
by scripts/choose_pattern.py. The autouse TestModel override fixture in
tests/conftest.py picks this agent up automatically (it scans every module
under agent.agents for Agent instances), so no fixture changes are needed.
"""

from agent.agents.{name} import {Name}Deps, {name}_agent


async def test_{name}_agent_runs_with_test_model():
    result = await {name}_agent.run("Smoke test input", deps={Name}Deps())
    assert result.output is not None
'''


def to_pascal_case(name: str) -> str:
    return "".join(word.capitalize() for word in name.split("_"))


def validate_name(name: str) -> str | None:
    """Return an error message if name is invalid, else None."""
    if not NAME_RE.match(name):
        return (
            f"'{name}' is not a valid snake_case identifier "
            "(must start with a lowercase letter, then lowercase letters/digits/underscores)"
        )
    if keyword.iskeyword(name):
        return f"'{name}' is a Python keyword"
    if name in RESERVED_NAMES:
        return f"'{name}' is reserved (collides with the primary-agent wiring or an existing stub)"

    agent_module = AGENTS_DIR / f"{name}.py"
    prompt_file = PROMPTS_DIR / f"{name}.txt"
    test_module = TESTS_DIR / f"test_agents_{name}.py"
    for path in (agent_module, prompt_file, test_module):
        if path.exists():
            return f"{path.relative_to(REPO_ROOT)} already exists"

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="snake_case name for the new agent, e.g. 'newsletter'")
    name = parser.parse_args().name

    error = validate_name(name)
    if error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    pascal_name = to_pascal_case(name)
    context = {"name": name, "Name": pascal_name}

    agent_module = AGENTS_DIR / f"{name}.py"
    prompt_file = PROMPTS_DIR / f"{name}.txt"
    test_module = TESTS_DIR / f"test_agents_{name}.py"

    agent_module.write_text(AGENT_MODULE_TEMPLATE.format(**context), encoding="utf-8")
    print(f"Created {agent_module.relative_to(REPO_ROOT)}")

    prompt_file.write_text(PROMPT_TEMPLATE.format(**context), encoding="utf-8")
    print(f"Created {prompt_file.relative_to(REPO_ROOT)}")

    test_module.write_text(TEST_MODULE_TEMPLATE.format(**context), encoding="utf-8")
    print(f"Created {test_module.relative_to(REPO_ROOT)}")

    # Reformat the generated Python files with ruff so line-wrapping matches
    # repo style regardless of how long `name` is — hand-formatting a
    # template for every possible identifier length isn't reliable.
    try:
        subprocess.run(
            ["ruff", "format", str(agent_module), str(test_module)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"warning: could not auto-format generated files with ruff ({exc})", file=sys.stderr)
        print("  run `uv run ruff format .` manually", file=sys.stderr)

    print(
        f"\nDone — the {name} agent is scaffolded as an independent module.\n"
        f"agent/agents/__init__.py was NOT touched; import this agent directly:\n"
        f"    from agent.agents.{name} import "
        f"{pascal_name}Deps, {pascal_name}Output, {name}_agent, run_{name}_agent\n\n"
        f"Next steps:\n"
        f"  1. Edit agent/agents/{name}.py's output schema and agent/prompts/{name}.txt\n"
        f"  2. uv run pytest  (runs the new smoke test under TestModel, no API key needed)\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
