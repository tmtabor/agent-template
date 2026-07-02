# Agent Template — Implementation Guide

This file contains everything needed to implement this project from scratch. It is a historical build spec, not day-to-day guidance — for working in the repo as it exists now, see `CLAUDE.md`. Every architectural decision documented here was made deliberately; if you're rebuilding a piece of this template from scratch, do not deviate without good reason.

---

## Project Purpose

A clean, opinionated, general-purpose Python AI agent template. The goal is to be able to clone this repo and start building a production-quality agentic AI project as fast as possible — with observability, evals, and error handling pre-configured and ready to use. Designed to be used as a starting point for interview coding challenges and real projects.

**Design philosophy: maximum signal, minimum noise.** Every file must have a clear reason to exist. Do not add files, directories, or abstractions speculatively. If something is not needed right now, it is not in the template.

---

## Final Directory Structure

Implement exactly this structure, no more, no less:

```
agent-template/
├── .env.example
├── .python-version
├── .gitignore
├── CLAUDE.md                    ← short day-to-day guide for this repo (not this file)
├── IMPLEMENTATION_GUIDE.md      ← this file — the full from-scratch build spec
├── README.md
├── pyproject.toml
│
├── agent/
│   ├── __init__.py
│   ├── config.py                ← pydantic-settings: validates env vars at startup
│   ├── logging.py               ← logfire setup, stdlib routing, instrument_pydantic_ai
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── single.py            ← stub: simple single-agent loop
│   │   ├── supervisor.py        ← stub: supervisor/worker multi-agent pattern
│   │   └── tool_calling.py      ← stub: tool-calling agent
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   └── example.py           ← full tool pattern with validation and error handling
│   │
│   └── prompts/
│       ├── templates.py         ← load_prompt() utility: loads .txt files from this dir
│       └── system.txt           ← default system prompt template
│
├── evals/
│   ├── __init__.py
│   ├── conftest.py              ← pytest fixtures for eval runs
│   ├── judge.py                 ← LLM-as-judge scorer (judge agent + verdict)
│   ├── fixtures/
│   │   └── example.json         ← 2-3 example eval cases showing the schema
│   ├── test_pass_fail.py        ← pass/fail eval examples
│   └── test_llm_judge.py        ← LLM-as-judge eval examples
│
└── tests/
    ├── __init__.py
    ├── conftest.py              ← pytest fixtures, TestModel setup
    └── test_example.py          ← example unit tests using TestModel (no API calls)
```

---

## Technology Stack

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.13 | Pin in `.python-version`. Conservative pin — verify pydantic-ai/logfire support a newer Python before bumping. |
| uv | latest | Package manager. All commands via `uv run`. |
| pydantic-ai | `>=2.1.0` | V2 API only — see critical API notes below. |
| pydantic-evals | `>=2.1.0` | Eval framework. Separate package — not pulled in by `pydantic-ai`; must be declared explicitly. |
| pydantic-settings | `>=2.0` | For `config.py` — validates env vars at startup. |
| logfire | `>=3.0` | Observability. No `[pydantic-ai]` extra exists — `instrument_pydantic_ai()` works with the base package. |
| pytest | `>=8.0` | Test runner. |
| pytest-asyncio | `>=0.24` | Required for async agent tests. |
| ruff | `>=0.8` | Linting and formatting. Replaces black + flake8. |

---

## pyproject.toml

```toml
[project]
name = "agent-template"
version = "0.1.0"
description = "Opinionated general-purpose AI agent template"
requires-python = ">=3.13"
dependencies = [
    "pydantic-ai>=2.1.0",
    "pydantic-settings>=2.0",
    "logfire>=3.0",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pydantic-evals>=2.1.0",
    "ruff>=0.8",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "eval: marks tests as evals (require an API key; run with -m eval, skipped by default)",
]
addopts = "-m 'not eval'"

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
ignore = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["agent"]
```

The `addopts = "-m 'not eval'"` means `uv run pytest` runs only unit tests by default. To run all evals — including the LLM-as-judge evals, which make real API calls and cost money: `uv run pytest -m eval`.

---

## CRITICAL: Pydantic AI V2 API (Breaking Changes from V1)

Pydantic AI 2.0 was released June 23, 2026. V2 has several breaking changes from V1. Many tutorials and docs online still show the old V1 API. Use ONLY the V2 API.

### ❌ V1 (WRONG — do not use)
```python
# OLD: system_prompt parameter
agent = Agent('anthropic:claude-opus-4-8', system_prompt="You are helpful.")

# OLD: @agent.system_prompt decorator
@agent.system_prompt
def my_prompt() -> str:
    return "You are helpful."

# OLD: result_type parameter
agent = Agent('anthropic:claude-opus-4-8', result_type=MyModel)

# OLD: result.data accessor
output = result.data

# OLD: evals import
from pydantic_ai.evals import Dataset
```

### ✅ V2 (CORRECT — use these)
```python
# NEW: instructions parameter
agent = Agent('anthropic:claude-opus-4-8', instructions="You are helpful.")

# NEW: @agent.instructions decorator
@agent.instructions
def my_instructions() -> str:
    return "You are helpful."

# NEW: output_type parameter
agent = Agent('anthropic:claude-opus-4-8', output_type=MyModel)

# NEW: result.output accessor
output = result.output

# NEW: evals import from separate package
from pydantic_evals import Dataset, Case
```

### Other V2 API notes
- `AgentRunResult.data` is removed → use `result.output`
- `Agent.last_run_messages` is removed → use `result.all_messages()` or `result.new_messages()`
- `@agent.result_validator` is removed → use `@agent.output_validator`
- Instrumentation: token usage now reported under `gen_ai.aggregated_usage.*` on run spans (not `gen_ai.usage.*`) to avoid double-counting. Set `use_aggregated_usage_attribute_names=False` in `InstrumentationSettings` to revert.
- `pydantic_evals.EvaluationReport` and `ReportCase` are now generic dataclasses, not Pydantic models. Use `EvaluationReportAdapter` / `ReportCaseAdapter` for serialization, not `model_dump()`.
- `EvaluationReport.print()` and `console_table()` now require keyword arguments.

---

## config.py — Environment Variable Validation

Use `pydantic-settings` to validate required environment variables at startup. A `model_validator` fails fast with a clear error when the selected model's provider requires an API key that isn't set (Anthropic and OpenAI require keys; local Ollama does not) — rather than failing cryptically at the first API call.

```python
# agent/config.py
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Validated at startup: if the selected model's provider requires an API
    key and it is missing, Settings() raises immediately with a clear error
    instead of failing cryptically at the first API call.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Provider API keys — required only for the provider of the selected model
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Model selection — model-agnostic, defaults to Claude Opus 4.8
    model: str = "anthropic:claude-opus-4-8"

    # Judge model for LLM-as-judge evals. Use a different model from the agent
    # to avoid self-assessment bias, but at least as capable — a weak judge
    # grading a strong agent introduces its own bias.
    judge_model: str = "anthropic:claude-sonnet-5"

    # Logfire — optional, falls back to console if not set
    logfire_token: str | None = None

    # Logging
    log_level: str = "INFO"

    @model_validator(mode="after")
    def check_provider_key(self) -> "Settings":
        """Fail fast if the selected model's provider key is missing.

        Only the agent model is validated here — the judge model is used
        only by evals, which require a real key at runtime anyway.
        """
        provider = self.model.split(":", 1)[0]
        if provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError(
                "MODEL is an Anthropic model but ANTHROPIC_API_KEY is not set. "
                "Add it to .env or the environment."
            )
        if provider == "openai" and not self.openai_api_key:
            raise ValueError(
                "MODEL is an OpenAI model but OPENAI_API_KEY is not set. "
                "Add it to .env or the environment."
            )
        # "ollama" (and other local providers) run locally — no API key needed.
        return self


settings = Settings()
```

Import everywhere as: `from agent.config import settings`

---

## logging.py — Logfire + Stdlib Routing

This is the single place where all observability is configured. It must do four things:

1. Configure Logfire with token from env (cloud) or console exporter as fallback
2. Route Python's stdlib `logging` through Logfire so third-party library logs appear in traces
3. Call `logfire.instrument_pydantic_ai()` so all agent runs are automatically traced
4. Expose a `get_logger(name)` helper for consistent logging across the codebase

```python
# agent/logging.py
import logging
import logfire
from agent.config import settings


def configure_logging() -> None:
    """Configure Logfire observability and stdlib logging routing.
    
    Call this once at application startup before creating any agents.
    
    If LOGFIRE_TOKEN is set, traces are sent to Logfire cloud.
    If not set, traces are printed to the console (development mode).
    """
    logfire_kwargs: dict = {}
    
    if settings.logfire_token:
        logfire_kwargs["token"] = settings.logfire_token
    else:
        # Console fallback for local development — no token required
        logfire_kwargs["send_to_logfire"] = False
        logfire_kwargs["console"] = logfire.ConsoleOptions(
            min_log_level="debug",
            include_timestamps=True,
        )
    
    logfire.configure(**logfire_kwargs)
    
    # Instrument Pydantic AI — automatically traces all agent runs,
    # tool calls, model requests, and validation retries
    logfire.instrument_pydantic_ai()
    
    # Route stdlib logging through Logfire so third-party library logs
    # (httpx, anthropic SDK, etc.) appear in traces alongside agent spans
    logging.basicConfig(handlers=[logfire.LogfireLoggingHandler()])
    
    # Set root log level from config
    logging.getLogger().setLevel(settings.log_level.upper())


def get_logger(name: str) -> logging.Logger:
    """Get a stdlib logger that routes through Logfire.
    
    Usage: logger = get_logger(__name__)
    """
    return logging.getLogger(name)
```

**Important:** `configure_logging()` must be called once at startup, before any agents are created or run. In agent stubs, call it at the top of `if __name__ == "__main__":` blocks or in a startup function.

---

## Agent Stubs

Three stub patterns. Each is a working skeleton that demonstrates the pattern with clear comments showing what to fill in. They should be runnable as-is (returning placeholder output) and easy to extend.

### single.py — Simple Single-Agent Loop

The most common pattern. One agent, one run, returns output.

```python
# agent/agents/single.py
"""Single-agent pattern: one agent handles the entire task.

This is the simplest pattern — use it when:
- One agent can handle the full task
- No specialization or delegation is needed
- You want the lowest complexity

To use:
    1. Define your output type (or use str for unstructured output)
    2. Set your instructions
    3. Add tools if needed
    4. Call run_agent()
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import (  # noqa: F401 — RunContext used in commented tool example below
    Agent,
    RunContext,
)

from agent.config import settings
from agent.logging import configure_logging, get_logger
from agent.prompts.templates import load_prompt

logger = get_logger(__name__)


# --- Output type ---
# Replace with your actual output schema, or use str for unstructured output.
class AgentOutput(BaseModel):
    """Replace with your actual output schema."""
    result: str
    confidence: float


# --- Dependencies ---
# Use a dataclass to inject runtime dependencies (DB connections, API clients, etc.)
# Remove if your agent needs no external dependencies.
@dataclass
class AgentDeps:
    """Runtime dependencies injected into the agent."""
    # example_client: SomeAPIClient  # Add your dependencies here
    pass


# --- Agent definition ---
agent: Agent[AgentDeps, AgentOutput] = Agent(
    settings.model,
    output_type=AgentOutput,
    deps_type=AgentDeps,
    instructions=load_prompt("system"),  # loads agent/prompts/system.txt
    # Or inline: instructions="You are a helpful assistant."
)


# --- Tools ---
# Add tools here. See agent/tools/example.py for the full pattern.
# @agent.tool
# async def my_tool(ctx: RunContext[AgentDeps], query: str) -> str:
#     """Tool description — this docstring is sent to the LLM."""
#     return "result"


# --- Dynamic instructions (optional) ---
# Use @agent.instructions for instructions that depend on runtime state.
# @agent.instructions
# async def dynamic_instructions(ctx: RunContext[AgentDeps]) -> str:
#     return f"Today is {date.today()}."


async def run_agent(user_input: str, deps: AgentDeps | None = None) -> AgentOutput:
    """Run the agent with the given user input.
    
    Args:
        user_input: The user's message or task description.
        deps: Runtime dependencies. Created with defaults if not provided.
    
    Returns:
        Validated AgentOutput instance.
    """
    if deps is None:
        deps = AgentDeps()
    
    logger.info("Running single agent", extra={"user_input": user_input})
    
    result = await agent.run(user_input, deps=deps)
    
    logger.info("Agent run complete", extra={"output": result.output})
    return result.output


# --- Multi-turn conversation example ---
# To maintain conversation history across multiple calls:
#
# history = []
# result1 = await agent.run("First message", deps=deps)
# history = result1.all_messages()
#
# result2 = await agent.run("Follow-up", deps=deps, message_history=history)
# history = result2.all_messages()
#
# Use all_messages(), not new_messages(), when carrying history forward —
# new_messages() returns only the messages from that single run, so assigning
# it to history would silently drop all earlier turns.


if __name__ == "__main__":
    import asyncio
    configure_logging()
    output = asyncio.run(run_agent("Hello, what can you do?"))
    print(output)
```

### supervisor.py — Supervisor/Worker Multi-Agent Pattern

```python
# agent/agents/supervisor.py
"""Supervisor/worker multi-agent pattern.

Use this pattern when:
- A task can be broken into specialized subtasks
- Different agents have different tools, instructions, or output types
- You want a coordinator to manage escalation and routing

Architecture:
    supervisor_agent → decides which worker to call
    worker_agent_a   → handles task type A
    worker_agent_b   → handles task type B

To use:
    1. Define worker agents with their specialized tools and instructions
    2. Give the supervisor tools that delegate to workers
    3. The supervisor orchestrates; workers execute
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from agent.config import settings
from agent.logging import configure_logging, get_logger

logger = get_logger(__name__)


# --- Shared dependencies ---
@dataclass
class SharedDeps:
    """Dependencies shared across supervisor and worker agents."""
    pass


# --- Worker agents ---
# Each worker is a specialized agent with its own instructions and tools.

class WorkerAOutput(BaseModel):
    result: str


worker_agent_a: Agent[SharedDeps, WorkerAOutput] = Agent(
    settings.model,
    output_type=WorkerAOutput,
    deps_type=SharedDeps,
    instructions="You are a specialist in [TASK TYPE A]. [Add specific instructions.]",
)

# Add worker_agent_b, worker_agent_c etc. as needed


# --- Supervisor agent ---
class SupervisorOutput(BaseModel):
    final_result: str
    steps_taken: list[str]


supervisor_agent: Agent[SharedDeps, SupervisorOutput] = Agent(
    settings.model,
    output_type=SupervisorOutput,
    deps_type=SharedDeps,
    instructions="""You are a supervisor coordinating specialized workers.
    
    Analyze the task, delegate to the appropriate worker, and synthesize results.
    Use the available delegation tools to call workers.
    """,
)


# --- Supervisor tools that delegate to workers ---
@supervisor_agent.tool
async def delegate_to_worker_a(ctx: RunContext[SharedDeps], task: str) -> str:
    """Delegate a [TASK TYPE A] task to the specialized worker.
    
    Args:
        task: The specific task for the worker to complete.
    
    Returns:
        The worker's result as a string.
    """
    logger.info("Delegating to worker A", extra={"task": task})
    result = await worker_agent_a.run(task, deps=ctx.deps)
    return result.output.result


# Add more delegation tools for other workers


async def run_supervisor(user_input: str) -> SupervisorOutput:
    """Run the supervisor agent to coordinate workers on a task."""
    deps = SharedDeps()
    logger.info("Running supervisor agent", extra={"user_input": user_input})
    result = await supervisor_agent.run(user_input, deps=deps)
    return result.output


if __name__ == "__main__":
    import asyncio
    configure_logging()
    output = asyncio.run(run_supervisor("Complete this complex task..."))
    print(output)
```

### tool_calling.py — Tool-Calling Agent

```python
# agent/agents/tool_calling.py
"""Tool-calling agent pattern.

Use this pattern when:
- The agent needs to interact with external systems (APIs, databases, files)
- You want the LLM to decide which tools to call and when
- Tool results inform subsequent decisions (agentic loop)

Key design principles (from production experience):
- Keep tool interfaces simple: fewer optional params = more reliable tool selection
- Translate errors into English: give the LLM enough context to self-correct
- Hold large payloads at the tool layer: don't dump raw API responses into context

See agent/tools/example.py for the full tool implementation pattern.
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext

from agent.config import settings
from agent.logging import configure_logging, get_logger

logger = get_logger(__name__)


# --- Dependencies ---
@dataclass
class ToolAgentDeps:
    """Runtime dependencies for the tool-calling agent."""
    # Add API clients, DB connections, etc.
    # example (requires `from dataclasses import field`):
    # api_client: MyAPIClient = field(default_factory=MyAPIClient)
    pass


# --- Output type ---
class ToolAgentOutput(BaseModel):
    answer: str
    # Pydantic deep-copies mutable defaults, so a plain [] is safe here.
    # Do NOT use dataclasses.field() inside a BaseModel — it is not a
    # Pydantic construct (use pydantic.Field(default_factory=...) if needed).
    tools_used: list[str] = []


# --- Agent ---
tool_agent: Agent[ToolAgentDeps, ToolAgentOutput] = Agent(
    settings.model,
    output_type=ToolAgentOutput,
    deps_type=ToolAgentDeps,
    instructions="""You are an agent with access to tools.
    
    Use tools when you need external information or to take actions.
    If a tool fails, read the error message carefully — it will tell you how to recover.
    """,
)


# --- Tools ---
# See agent/tools/example.py for the full pattern with proper error handling.

@tool_agent.tool
async def example_tool(ctx: RunContext[ToolAgentDeps], query: str) -> str:
    """Search for information about the given query.
    
    Args:
        query: What to search for. Be specific.
    
    Returns:
        Relevant information as a string.
    
    Raises:
        ModelRetry: When the tool fails in a way the LLM can correct.
    """
    try:
        # Replace with real implementation
        logger.info("Tool called", extra={"tool": "example_tool", "query": query})
        return f"Result for: {query}"
    except ValueError as e:
        # Translate errors into English so the LLM can self-correct
        raise ModelRetry(
            f"Invalid query format: {e}. "
            "Please provide a query as a plain text string."
        ) from e
    except Exception as e:
        # Unrecoverable: log and re-raise. ModelRetry is only for errors the
        # LLM can correct by changing its input (see agent/tools/example.py).
        logger.error("Tool failed", extra={"tool": "example_tool", "error": str(e)})
        raise


async def run_tool_agent(user_input: str) -> ToolAgentOutput:
    """Run the tool-calling agent."""
    deps = ToolAgentDeps()
    logger.info("Running tool-calling agent", extra={"user_input": user_input})
    result = await tool_agent.run(user_input, deps=deps)
    return result.output


if __name__ == "__main__":
    import asyncio
    configure_logging()
    output = asyncio.run(run_tool_agent("What can you find out about Python 3.13?"))
    print(output)
```

---

## tools/example.py — Full Tool Pattern

This is the canonical tool implementation pattern. It demonstrates:
- Pydantic input validation via typed parameters
- English-language error messages for LLM recovery (key insight from production MCP work)
- Structured logging of tool calls and results
- `ModelRetry` for recoverable errors vs. exceptions for unrecoverable ones

```python
# agent/tools/example.py
"""Example tool demonstrating the full production tool pattern.

Copy this file and modify for your specific tool. Key principles:
- Simple interfaces: avoid optional parameters where possible
- English errors: error messages should tell the LLM how to recover
- Log inputs and outputs: essential for debugging agentic loops
- Use ModelRetry for LLM-recoverable errors
- Use regular exceptions for unrecoverable failures
"""
from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext

from agent.logging import get_logger

logger = get_logger(__name__)

# Type alias for deps — replace with your actual deps type when copying
type AnyDeps = object


async def search_tool(ctx: RunContext[AnyDeps], query: str, max_results: int = 5) -> str:
    """Search for information matching the query.
    
    This docstring is sent to the LLM as the tool description.
    Be specific about what this tool does and when to use it.
    
    Args:
        query: Search query string. Must be non-empty.
        max_results: Maximum number of results to return (1-20).
    
    Returns:
        Search results as a formatted string, one result per line.
        Returns "No results found" if nothing matches.
    
    Raises:
        ModelRetry: When input is invalid or the search service is temporarily unavailable.
    """
    # --- Input validation ---
    if not query or not query.strip():
        raise ModelRetry(
            "The query parameter cannot be empty. "
            "Please provide a specific search query string."
        )
    
    if not 1 <= max_results <= 20:
        raise ModelRetry(
            f"max_results must be between 1 and 20, got {max_results}. "
            "Please use a value in that range."
        )
    
    # --- Log the tool call ---
    logger.debug(
        "Tool call: search",
        extra={"query": query, "max_results": max_results}
    )
    
    try:
        # Replace with real implementation
        results = [f"Result {i} for '{query}'" for i in range(1, max_results + 1)]
        
        if not results:
            return "No results found for this query. Try broadening your search terms."
        
        # --- Hold large payloads at tool layer ---
        # If results could be large, summarize or paginate here rather than
        # returning raw data that might overflow the context window.
        output = "\n".join(results[:max_results])
        
        # --- Log the result ---
        logger.debug(
            "Tool result: search",
            extra={"result_count": len(results), "query": query}
        )
        
        return output
        
    except ConnectionError as e:
        # Recoverable: service temporarily unavailable, LLM can retry
        raise ModelRetry(
            f"Search service is temporarily unavailable: {e}. "
            "Please try again in a moment."
        ) from e
    except Exception as e:
        # Unrecoverable: log and re-raise. Reserve ModelRetry for errors the
        # LLM can plausibly fix by changing its input — asking it to retry an
        # unknown failure just burns the agent's retry budget.
        logger.error(
            "Tool failed: search",
            extra={"error": str(e), "query": query}
        )
        raise
```

To register this tool with an agent, import and decorate:
```python
from agent.tools.example import search_tool

@my_agent.tool
async def search(ctx: RunContext[MyDeps], query: str) -> str:
    return await search_tool(ctx, query)
```

---

## prompts/templates.py and system.txt

### templates.py

```python
# agent/prompts/templates.py
"""Prompt template loader.

Loads system prompts from .txt files in this directory.
Centralizes prompt loading so all agents use the same pattern.
"""
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load a prompt template from a .txt file.
    
    Args:
        name: Filename without extension (e.g., "system" loads "system.txt")
    
    Returns:
        The prompt text as a string.
    
    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    prompt_path = PROMPTS_DIR / f"{name}.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path}. "
            f"Available prompts: {[f.stem for f in PROMPTS_DIR.glob('*.txt')]}"
        )
    return prompt_path.read_text(encoding="utf-8").strip()
```

### system.txt

The default system prompt. Agents can override with their own or use this as a base.

```
You are a helpful, accurate, and concise AI assistant.

When using tools:
- Use tools when they provide information you don't have
- Read error messages carefully — they tell you how to recover
- If a tool fails, try to recover before giving up

When responding:
- Be direct and specific
- Acknowledge uncertainty when you're not sure
- Ask for clarification if the request is ambiguous
```

---

## Evals — pydantic_evals

### Critical: Import path

Evals are in the `pydantic_evals` package (separate from `pydantic_ai`):
```python
from pydantic_evals import Dataset, Case
from pydantic_evals.evaluators import LLMJudge, IsInstance, Equals
```

### evals/fixtures/example.json

```json
[
  {
    "name": "basic_greeting",
    "inputs": {"user_input": "Hello, how are you?"},
    "metadata": {
      "expected_topics": ["greeting", "response"],
      "difficulty": "easy"
    }
  },
  {
    "name": "factual_question",
    "inputs": {"user_input": "What is the capital of France?"},
    "expected_output": "Paris",
    "metadata": {
      "expected_topics": ["geography", "factual"],
      "difficulty": "easy"
    }
  },
  {
    "name": "complex_task",
    "inputs": {"user_input": "Summarize the key benefits of async programming in Python."},
    "metadata": {
      "expected_topics": ["python", "async", "concurrency"],
      "difficulty": "medium"
    }
  }
]
```

### evals/conftest.py

```python
# evals/conftest.py
"""Pytest fixtures for eval runs."""
import json
from pathlib import Path

import pytest

from agent.logging import configure_logging


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Configure logging once for the eval session."""
    configure_logging()


@pytest.fixture
def example_fixtures() -> list[dict]:
    """Load example eval fixtures from JSON."""
    fixtures_path = Path(__file__).parent / "fixtures" / "example.json"
    return json.loads(fixtures_path.read_text())
```

### evals/judge.py — LLM-as-Judge Scorer

```python
# evals/judge.py
"""LLM-as-judge evaluator for semantic quality scoring.

Uses a separate judge model (settings.judge_model) to evaluate agent outputs.
The judge should be a *different* model from the agent under test to avoid
self-assessment bias, but at least as capable — a weak judge grading a strong
agent introduces its own bias.
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from agent.config import settings


class JudgeScore(BaseModel):
    """Structured output produced by the judge model."""
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str


@dataclass
class JudgeVerdict:
    """Judge score plus the threshold decision.

    `passed` is computed from the threshold, never LLM-generated — don't ask
    the model to produce a value the code immediately overwrites.
    """
    score: float
    reasoning: str
    passed: bool


judge_agent: Agent[None, JudgeScore] = Agent(
    settings.judge_model,
    output_type=JudgeScore,
    instructions="""You are an impartial evaluator assessing AI agent outputs.
    
    Score the response on a scale of 0.0 to 1.0:
    - 1.0: Perfect response, fully addresses the task
    - 0.7-0.9: Good response with minor issues
    - 0.4-0.6: Partial response, addresses some but not all requirements  
    - 0.0-0.3: Poor response, fails to address the task
    
    Be objective and focus on whether the response fulfills the stated requirements.
    """,
)


async def judge_response(
    task: str,
    response: str,
    criteria: str,
    threshold: float = 0.7,
) -> JudgeVerdict:
    """Evaluate a response using an LLM judge.
    
    Args:
        task: The original task or question given to the agent.
        response: The agent's response to evaluate.
        criteria: Specific criteria the response should meet.
        threshold: Minimum score to pass (default 0.7).
    
    Returns:
        JudgeVerdict with score, reasoning, and pass/fail.
    """
    prompt = f"""Task: {task}

Response to evaluate:
{response}

Evaluation criteria:
{criteria}

Score this response and explain your reasoning."""
    
    result = await judge_agent.run(prompt)
    score = result.output
    return JudgeVerdict(
        score=score.score,
        reasoning=score.reasoning,
        passed=score.score >= threshold,
    )
```

### evals/test_pass_fail.py — Pass/Fail Eval Examples

```python
# evals/test_pass_fail.py
"""Pass/fail eval examples using pydantic_evals.

These evals test for specific, verifiable outputs.
Run with: uv run pytest -m eval
"""
import pytest

from agent.agents.single import run_agent


@pytest.mark.eval
@pytest.mark.asyncio
async def test_agent_returns_output():
    """Basic smoke test: agent runs without error and returns output."""
    output = await run_agent("Say hello.")
    assert output is not None
    assert output.result  # non-empty result


@pytest.mark.eval
@pytest.mark.asyncio
async def test_agent_handles_empty_ish_input():
    """Agent should handle minimal input gracefully."""
    output = await run_agent("Hi.")
    assert output is not None


@pytest.mark.eval
@pytest.mark.asyncio
async def test_agent_confidence_in_range():
    """Agent output confidence should be between 0 and 1."""
    output = await run_agent("What is 2 + 2?")
    assert 0.0 <= output.confidence <= 1.0


# --- pydantic_evals Dataset pattern ---
# For more structured evals with datasets, use this pattern:
#
# from pydantic_evals import Dataset, Case
#
# dataset = Dataset(cases=[
#     Case(name="greeting", inputs={"user_input": "Hello!"}, expected_output=...),
#     Case(name="math", inputs={"user_input": "What is 2+2?"}, expected_output=...),
# ])
#
# @pytest.mark.eval
# async def test_dataset():
#     report = await dataset.evaluate(lambda inputs: run_agent(inputs["user_input"]))
#     report.print(include_input=True, include_output=True, include_scores=True)
#     assert report.averages().total_score >= 0.8
```

### evals/test_llm_judge.py — LLM-as-Judge Eval Examples

```python
# evals/test_llm_judge.py
"""LLM-as-judge eval examples.

These evals use a separate LLM (settings.judge_model) to evaluate output
quality. They require an API key and cost money to run.
Run with: uv run pytest -m eval  (runs alongside the pass/fail evals)
"""
import pytest

from agent.agents.single import run_agent
from evals.judge import judge_response


@pytest.mark.eval
@pytest.mark.asyncio
async def test_agent_quality_judge():
    """LLM judge evaluates response quality."""
    task = "Explain what an AI agent is in one sentence."
    output = await run_agent(task)
    
    verdict = await judge_response(
        task=task,
        response=output.result,
        criteria="The response should be a single sentence that accurately "
                 "describes what an AI agent is. It should be clear and concise.",
        threshold=0.7,
    )
    
    assert verdict.passed, (
        f"Judge score {verdict.score:.2f} below threshold. "
        f"Reasoning: {verdict.reasoning}"
    )


@pytest.mark.eval
@pytest.mark.asyncio
async def test_agent_relevance_judge():
    """LLM judge evaluates whether response is relevant to the task."""
    task = "List three benefits of Python for data science."
    output = await run_agent(task)
    
    verdict = await judge_response(
        task=task,
        response=output.result,
        criteria="The response should list exactly three distinct benefits of Python "
                 "specifically for data science use cases.",
        threshold=0.6,
    )
    
    assert verdict.passed, (
        f"Relevance score {verdict.score:.2f} below threshold. "
        f"Reasoning: {verdict.reasoning}"
    )
```

---

## Tests — Unit Tests with TestModel

Unit tests should NEVER make real API calls. Use `TestModel` to simulate agent behavior.

Unit tests must also pass with **no real API key configured**. Two things can demand a key before `TestModel` ever takes over: `Settings` validates the selected provider's key at import time, and the module-level `Agent(settings.model, ...)` constructions may instantiate a provider client eagerly. `tests/conftest.py` therefore sets dummy keys before anything under `agent/` is imported — this is deliberate; do not remove it. (Evals intentionally do NOT do this: a missing key there should fail loudly at startup rather than at the first paid API call.)

### tests/conftest.py

```python
# tests/conftest.py
"""Pytest fixtures for unit tests."""
import os

# Unit tests must run with no real credentials and no API calls. Settings
# requires a provider key for the selected model at import time, and the
# module-level Agent construction may create a provider client that also
# wants a key — set dummy values before anything under agent/ is imported.
# setdefault() leaves real keys untouched if they are present.
os.environ.setdefault("ANTHROPIC_API_KEY", "unit-test-dummy-key")
os.environ.setdefault("OPENAI_API_KEY", "unit-test-dummy-key")

import pytest  # noqa: E402

from agent.logging import configure_logging  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Configure logging once for the test session."""
    configure_logging()
```

### tests/test_example.py

```python
# tests/test_example.py
"""Example unit tests using TestModel — no API calls, no cost.

TestModel simulates agent behavior for fast, deterministic unit tests.
Import it from: from pydantic_ai.models.test import TestModel
"""
import pytest
from pydantic_ai.models.test import TestModel

from agent.agents.single import AgentDeps, agent


@pytest.mark.asyncio
async def test_agent_runs_with_test_model():
    """Agent runs without error using TestModel (no API call)."""
    with agent.override(model=TestModel()):
        result = await agent.run("Test input", deps=AgentDeps())
    # TestModel returns a placeholder output that satisfies the output_type schema
    assert result.output is not None


@pytest.mark.asyncio
async def test_agent_accepts_string_input():
    """Agent accepts a string user prompt."""
    with agent.override(model=TestModel()):
        result = await agent.run("Hello", deps=AgentDeps())
    assert result is not None


@pytest.mark.asyncio
async def test_agent_message_history():
    """Demonstrate multi-turn conversation history pattern."""
    with agent.override(model=TestModel()):
        result1 = await agent.run("First message", deps=AgentDeps())
        history = result1.all_messages()  # all_messages() — see single.py multi-turn note
        
        result2 = await agent.run(
            "Follow-up message",
            deps=AgentDeps(),
            message_history=history,
        )
    
    assert result2.output is not None
    # History from both turns is available
    assert len(result2.all_messages()) > len(result1.all_messages())
```

---

## .env.example

```bash
# Copy to .env and fill in your values
# Required when MODEL is an Anthropic model (default)
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Required when MODEL is an OpenAI model
# OPENAI_API_KEY=your_openai_api_key_here

# Model selection (default: anthropic:claude-opus-4-8)
# MODEL=anthropic:claude-opus-4-8
# MODEL=anthropic:claude-sonnet-5
# MODEL=ollama:llama3.3            # local Ollama — no API key required

# Judge model for LLM-as-judge evals (default: anthropic:claude-sonnet-5)
# JUDGE_MODEL=anthropic:claude-sonnet-5

# Logfire observability (optional — console output used if not set)
# LOGFIRE_TOKEN=your_logfire_token_here

# Logging level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
```

---

## .python-version

```
3.13
```

---

## .gitignore

```
.env
.venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.ruff_cache/
dist/
*.egg-info/
.DS_Store
logfire_credentials.json
```

---

## README.md

```markdown
# Agent Template

Opinionated general-purpose AI agent template. Clone and start building.

## Stack
- Python 3.13, uv
- Pydantic AI v2 (agents, tools) + pydantic-evals (evals)
- Logfire (observability)
- pytest + pytest-asyncio

## Quickstart

```bash
# Install dependencies
uv sync --group dev

# After uv sync, install Claude Code skills for pydantic-ai and logfire
uvx library-skills install --all --claude

# Copy and configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Run unit tests (no API calls, no API key needed)
uv run pytest

# Run all evals, including LLM-as-judge (requires API key, costs money)
uv run pytest -m eval

# Lint
uv run ruff check .

# Format
uv run ruff format .
```

## Agent patterns

Three stubs are provided — pick one and delete the others:

- `agent/agents/single.py` — one agent, one task
- `agent/agents/supervisor.py` — supervisor delegates to specialized workers  
- `agent/agents/tool_calling.py` — agent with tools that call external systems

Note: `tests/` and `evals/` import from `agent/agents/single.py`. If you delete
it, update those imports to point at the stub you kept.

## Adding tools

Copy `agent/tools/example.py`, implement your tool, register with `@agent.tool`.

## Observability

Set `LOGFIRE_TOKEN` for Logfire cloud. Without it, traces print to console.
All agent runs, tool calls, and model requests are automatically traced via
`logfire.instrument_pydantic_ai()`.

## Evals

- Pass/fail evals: `evals/test_pass_fail.py`
- LLM-as-judge evals: `evals/test_llm_judge.py`
- Add fixtures: `evals/fixtures/`

Run all evals (requires API key; the LLM-judge evals cost money): `uv run pytest -m eval`
```

---

## Implementation Notes for Claude Code

### Order of implementation
1. `pyproject.toml` and `.python-version` first — uv needs these to set up the environment
2. `.env.example` and `.gitignore`
3. `agent/config.py` — everything depends on this
4. `agent/logging.py` — everything depends on this
5. `agent/prompts/` — agents import from here
6. `agent/agents/` — the three stubs
7. `agent/tools/example.py`
8. `tests/` — unit tests
9. `evals/` — eval tests
10. `README.md` and `CLAUDE.md`

### Validation steps after implementation
```bash
uv sync --group dev           # dependencies install cleanly
uv run pytest                 # unit tests pass (TestModel, no API key needed)
uv run ruff check .           # no lint errors
uv run ruff format --check .  # no formatting issues
ANTHROPIC_API_KEY=dummy uv run python -c "from agent.config import settings; print(settings.model)"  # config loads (validator requires a key for the selected provider)
```

### Do not add
- A `Makefile` — uv commands are short enough
- A `docker-compose.yml` — add if the specific project needs it
- A `main.py` entry point — each agent stub has `if __name__ == "__main__":`
- A `base.py` for agents — Pydantic AI agents don't need inheritance
- A `memory/` directory — Pydantic AI handles conversation history natively via `message_history=`
- MCP server scaffolding — out of scope for agent template
- Web search module — it's a one-liner on the agent: `capabilities=[WebSearch()]`
- Any files not in the directory structure above
