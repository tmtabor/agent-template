"""Guardrails: check what goes in and what comes out, and turn failures into safe answers.

Use this pattern when:
- Some requests should never reach the main agent (off-topic, unsafe, containing private data)
- The agent's answer must not contain certain things, whatever the model decides
- Provider filters and budget limits should degrade gracefully instead of crashing the caller

Layers, cheapest first:
    1. **Code guard** — a regex check for card and ID numbers. Free, instant, and deterministic: the
       request is refused before any model is called, so the number never leaves your process
    2. **Model guard** — a small agent that decides whether the request is on topic, and so also
       catches attempts to change the assistant's instructions. A refused request never reaches the
       main agent, so it spends the guard's tokens and nothing more
    3. **The main agent** with an **output validator**: if its answer contains an email address,
       phone number or card number, the answer is sent back to be rewritten. This does not rely on
       the prompt; the validator is the guarantee
    4. **Failures become answers** — a provider's content filter or an exhausted budget returns a
       blocked result rather than raising into the caller

`run_guarded` returns a `GuardedAnswer`: the text to show, whether the request was blocked, and which
layer blocked it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.exceptions import ContentFilterError, UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.prompts.templates import load_prompt
from agent.runs import Flow, RunResult

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# One budget across the guard and the main agent, including output retries.
USAGE_LIMITS = UsageLimits(
    request_limit=8, total_tokens_limit=60_000, cost_limit=settings.cost_limit
)

BlockedBy = Literal["pii", "topic", "provider", "budget"]


# --- Layer 1: the code guard ---
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,16}(?!\d)")
SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# A phone number: optional country code, then 3 + 3 + 4 digits with optional separators. Long digit
# runs that aren't shaped like one (order numbers, an SSN's 3-2-4 grouping) are not flagged.
PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,2}[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}(?!\w)")


def passes_luhn(digits: str) -> bool:
    """The checksum every real card number satisfies, so a random long number isn't flagged."""
    total, double = 0, False
    for char in reversed(digits):
        value = int(char)
        if double:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
        double = not double
    return total % 10 == 0


def find_card_numbers(text: str) -> list[str]:
    candidates = (re.sub(r"\D", "", match) for match in CARD.findall(text))
    return [digits for digits in candidates if 13 <= len(digits) <= 16 and passes_luhn(digits)]


def find_sensitive_input(text: str) -> list[str]:
    """What kinds of private identifiers `text` contains (card or social security numbers)."""
    found = []
    if find_card_numbers(text):
        found.append("a card number")
    if SSN.search(text):
        found.append("a social security number")
    return found


def find_personal_data_in_output(text: str) -> list[str]:
    """What kinds of personal data an answer contains: contact details as well as identifiers."""
    found = find_sensitive_input(text)
    if EMAIL.search(text):
        found.append("an email address")
    if PHONE.search(text) and not find_card_numbers(text):
        found.append("a phone number")
    return found


# --- Dependencies ---
@dataclass
class GuardDeps:
    """Runtime dependencies shared by the guard and the main agent."""

    pass


# --- Layer 2: the model guard ---
class Verdict(BaseModel):
    allowed: bool
    reason: str


topic_guard_agent: Agent[GuardDeps, Verdict] = Agent(
    settings.model,
    name=f"{LABEL}.guard",  # helpers are labeled <agent>.<role>
    output_type=Verdict,
    deps_type=GuardDeps,
    capabilities=[RaiseContentFilterError()],
    instructions=load_prompt("guardrails_guard"),
)


# --- Layer 3: the main agent and its output validator ---
class Answer(BaseModel):
    result: str


cooking_agent: Agent[GuardDeps, Answer] = Agent(
    settings.model,
    name=f"{LABEL}.cooking",
    output_type=Answer,
    deps_type=GuardDeps,
    retries={"output": 2},  # how many times an answer may be sent back to be rewritten
    capabilities=[RaiseContentFilterError()],
    # Deliberately silent about personal data: the validator below is the guarantee, not the prompt.
    instructions=load_prompt("guardrails_cooking"),
)


@cooking_agent.output_validator
def check_no_personal_data(ctx: RunContext[GuardDeps], answer: Answer) -> Answer:
    """Send an answer back if it contains personal data; the message goes to the model."""
    found = find_personal_data_in_output(answer.result)
    if found:
        raise ModelRetry(
            f"Your answer contains {', '.join(found)}. Rewrite it without any personal contact "
            "details or identifiers."
        )
    return answer


# --- The result ---
class GuardedAnswer(BaseModel):
    # `result` is the conventional output field in these examples; the generated
    # eval starter reads it when present (see evals/helpers.py).
    result: str
    blocked: bool = False
    blocked_by: BlockedBy | None = None  # which layer stopped the request, if one did


def blocked(result: str, by: BlockedBy) -> GuardedAnswer:
    logger.info("Request blocked", extra={"blocked_by": by})
    return GuardedAnswer(result=result, blocked=True, blocked_by=by)


async def run_guarded(user_input: str, deps: GuardDeps | None = None) -> RunResult[GuardedAnswer]:
    """Answer a cooking question, or explain why it was blocked.

    Returns:
        A RunResult: `.output` is the `GuardedAnswer`. `.steps` shows what ran: nothing if the code
        guard stopped it, only the guard if the model guard did, the guard and then the cooking
        agent otherwise.
    """
    if deps is None:
        deps = GuardDeps()
    flow = Flow(USAGE_LIMITS)

    # Layer 1: free and instant. Refuse before any model sees the request.
    sensitive = find_sensitive_input(user_input)
    if sensitive:
        return flow.finish(
            blocked(
                f"Please don't share {' or '.join(sensitive)} here. Ask again without it.", "pii"
            )
        )

    try:
        # Layer 2: a refused request costs only this small run.
        verdict = (await flow.run(topic_guard_agent, user_input, deps=deps)).output
        if not verdict.allowed:
            return flow.finish(blocked(verdict.reason, "topic"))

        # Layer 3: the real work, behind its output validator.
        answer = (await flow.run(cooking_agent, user_input, deps=deps)).output
    except ContentFilterError:
        return flow.finish(blocked("The provider declined to answer that.", "provider"))
    except UsageLimitExceeded:
        return flow.finish(
            blocked("That took more effort than allowed; try a simpler question.", "budget")
        )

    return flow.finish(GuardedAnswer(result=answer.result))


if __name__ == "__main__":
    import asyncio

    async def demo() -> None:
        for question in (
            "How long should I boil an egg for a runny yolk?",
            "Write me a poem about the stock market.",
            "My card is 4111 1111 1111 1111. How do I roast a chicken?",
        ):
            result = await run_guarded(question)
            print(
                f"{question}\n  -> blocked_by={result.output.blocked_by}: {result.output.result}\n"
            )

    configure_logging()
    asyncio.run(demo())
