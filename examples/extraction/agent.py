"""Structured extraction: turn unstructured text into a validated schema.

Use this pattern when:
- The input is free text (emails, tickets, documents) and you need typed fields out
- Bad output should be caught and corrected, not passed downstream

How it works:
    1. `Contact` is the schema the model must fill in; keep it as flat as the data allows
    2. An output validator checks what the model returned and raises `ModelRetry` with a
       plain-English reason, so the model gets a chance to fix its own answer
    3. The retry budget is explicit; when it runs out the run fails loudly instead of
       returning something half-valid
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.prompts.templates import load_prompt

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# Guardrail against runaway agentic loops (see examples/single for the details).
USAGE_LIMITS = UsageLimits(
    request_limit=10, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)


# --- Output type ---
# Flat on purpose: nesting the data doesn't need makes small models fail validation.
class Contact(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None


# --- Dependencies ---
@dataclass
class ExtractionDeps:
    """Runtime dependencies injected into the extraction agent."""

    pass


# --- Agent definition ---
extraction_agent: Agent[ExtractionDeps, Contact] = Agent(
    settings.model,
    name=LABEL,
    output_type=Contact,
    deps_type=ExtractionDeps,
    # How many times the model may be sent back to fix a rejected answer.
    retries={"output": 2},
    capabilities=[RaiseContentFilterError()],
    instructions=load_prompt("extraction"),
)


# --- Validation ---
@extraction_agent.output_validator
def check_contact(ctx: RunContext[ExtractionDeps], contact: Contact) -> Contact:
    """Reject answers the model can plausibly fix; the message is sent back to it.

    ModelRetry is for errors the model can correct by changing its answer. Anything
    that is a bug in this code should raise normally instead.
    """
    if contact.email is not None and "@" not in contact.email:
        raise ModelRetry(
            f"'{contact.email}' is not an email address. Copy the address exactly as it "
            "appears in the text, or leave email empty if there isn't one."
        )
    if contact.email is None and contact.phone is None:
        raise ModelRetry("A contact needs an email address or a phone number; neither was found.")
    return contact


async def run_extraction(user_input: str, deps: ExtractionDeps | None = None) -> Contact:
    """Extract a contact from `user_input`.

    Raises:
        UnexpectedModelBehavior: When the model can't produce a valid contact within
            the retry budget. Callers decide what to do (retry later, queue for review).
    """
    if deps is None:
        deps = ExtractionDeps()
    logger.info("Running extraction agent", extra={"user_input": user_input})
    result = await extraction_agent.run(user_input, deps=deps, usage_limits=USAGE_LIMITS)
    return result.output


if __name__ == "__main__":
    import asyncio

    configure_logging()
    text = "Hi, it's Ada Lovelace from Analytical Engines Ltd. Reach me at ada@example.com."
    print(asyncio.run(run_extraction(text)))
