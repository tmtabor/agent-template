"""Router: a cheap classifier picks a specialist, and plain code does the dispatch.

Use this pattern when:
- Inputs fall into a known set of categories, each best handled by its own agent
- You want routing to be predictable, testable and cheap — not another LLM decision loop

How it differs from `supervisor`: there, the LLM decides which worker to call by using
delegation tools. Here the model only *classifies*; a dictionary in your code maps the
category to a specialist. Fewer moving parts, and the routing is plain Python you can test.

    classifier → category → SPECIALISTS[category] → answer
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.usage import RunUsage, UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# One budget for the whole route: the classifier and the specialist share a RunUsage
# (see run_router), so these limits bound the pair, not each call separately.
USAGE_LIMITS = UsageLimits(
    request_limit=10, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)

Category = Literal["billing", "technical", "general"]


@dataclass
class RouterDeps:
    """Runtime dependencies shared by the classifier and the specialists."""

    pass


# --- Classifier ---
class Classification(BaseModel):
    category: Category


router_agent: Agent[RouterDeps, Classification] = Agent(
    settings.model,
    name=f"{LABEL}.classifier",
    output_type=Classification,
    deps_type=RouterDeps,
    capabilities=[RaiseContentFilterError()],
    instructions="""Classify the support message into exactly one category:

    - billing: invoices, payments, refunds, plans and pricing
    - technical: errors, bugs, outages, how-to questions about the product
    - general: anything else
    """,
)


# --- Specialists ---
class Answer(BaseModel):
    result: str


def _specialist(category: Category, instructions: str) -> Agent[RouterDeps, Answer]:
    return Agent(
        settings.model,
        name=f"{LABEL}.{category}",
        output_type=Answer,
        deps_type=RouterDeps,
        capabilities=[RaiseContentFilterError()],
        instructions=instructions,
    )


# One specialist per category. Each can have its own instructions, tools, even model.
billing_agent = _specialist("billing", "You are a billing support specialist. Be precise.")
technical_agent = _specialist("technical", "You are a technical support engineer. Be concrete.")
general_agent = _specialist("general", "You are a friendly support agent. Keep answers short.")

SPECIALISTS: dict[Category, Agent[RouterDeps, Answer]] = {
    "billing": billing_agent,
    "technical": technical_agent,
    "general": general_agent,
}


class RouterOutput(BaseModel):
    result: str
    category: Category


async def run_router(user_input: str, deps: RouterDeps | None = None) -> RouterOutput:
    """Classify `user_input`, then answer it with the matching specialist."""
    if deps is None:
        deps = RouterDeps()
    usage = RunUsage()  # shared, so USAGE_LIMITS bounds the whole route

    classified = await router_agent.run(
        user_input, deps=deps, usage=usage, usage_limits=USAGE_LIMITS
    )
    category = classified.output.category
    logger.info("Routed", extra={"category": category})

    # The routing decision is a dictionary lookup, not an LLM call.
    specialist = SPECIALISTS[category]
    answered = await specialist.run(user_input, deps=deps, usage=usage, usage_limits=USAGE_LIMITS)
    return RouterOutput(result=answered.output.result, category=category)


if __name__ == "__main__":
    import asyncio

    configure_logging()
    print(asyncio.run(run_router("I was charged twice for my subscription this month.")))
