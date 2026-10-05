"""Retrieval-augmented generation: answer from documents, and cite only what was retrieved.

Use this pattern when:
- Answers must come from your own documents, not the model's memory
- Users need to see where an answer came from
- The model should say "I couldn't find that" rather than guess

How it works:
    1. A retrieval tool (`search_docs`) finds the passages relevant to a query
    2. The model answers from those passages and lists their ids as `sources`
    3. An output validator rejects any source the model did not actually retrieve, so a citation
       can be trusted: it points at something the model really saw

The knowledge base is a few invented store policies held in memory, scored by keyword overlap, so
the example runs anywhere with no dependencies. The policies are fictional on purpose: a model
cannot answer from memory, so a correct answer proves retrieval worked. Swap `search` for a vector
store or a search API and keep everything else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.usage import UsageLimits

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.prompts.templates import load_prompt
from agent.runs import Flow, RunResult

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# Guardrail against runaway agentic loops (see examples/single for the details). A multi-part
# question may search several times, so the request limit has headroom.
USAGE_LIMITS = UsageLimits(
    request_limit=12, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)

MAX_RESULTS = 3  # passages returned per search; keep context small and relevant


# --- The knowledge base ---
@dataclass(frozen=True)
class Passage:
    id: str
    title: str
    text: str


# Replace with your own documents. Fictional here, so correct answers can only come from retrieval.
KNOWLEDGE_BASE: tuple[Passage, ...] = (
    Passage(
        "returns-policy",
        "Returns",
        "Unworn items can be returned within 45 days of delivery for a full refund. Boots must be "
        "returned in their original box. Sale items are final sale and cannot be returned.",
    ),
    Passage(
        "shipping-rates",
        "Standard shipping",
        "Standard shipping is free on orders over $75 and costs $6.95 on smaller orders. Orders "
        "ship within 2 business days.",
    ),
    Passage(
        "express-shipping",
        "Express shipping",
        "Express shipping (2-day) costs $18. It is not available to Alaska, Hawaii or PO boxes.",
    ),
    Passage(
        "warranty-boots",
        "Boot warranty",
        "Birchwood boots carry a 3-year warranty against defects in materials and workmanship. "
        "Normal wear is not covered.",
    ),
    Passage(
        "warranty-packs",
        "Pack warranty",
        "Backpacks and duffels carry a lifetime warranty on zippers and stitching.",
    ),
    Passage(
        "store-hours",
        "Store hours",
        "The Portland flagship store is open 9am to 7pm Monday to Saturday and 11am to 5pm on "
        "Sunday.",
    ),
    Passage(
        "gift-cards",
        "Gift cards",
        "Gift cards never expire and can be used online or in store. They cannot be redeemed for "
        "cash.",
    ),
    Passage(
        "price-match",
        "Price matching",
        "We match the price of any authorized retailer on identical in-stock items within 14 days "
        "of purchase.",
    ),
    Passage(
        "loyalty",
        "Trail Club",
        "Trail Club members earn 1 point per dollar and get free shipping on every order, "
        "whatever the amount.",
    ),
    Passage(
        "repairs",
        "Repairs",
        "We repair boots and packs (soles, zippers, straps) for a flat $25 fee at any store or "
        "by mail.",
    ),
)


# --- Retrieval ---
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "the",
        "to",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
        "you",
        "your",
    ]
)


def tokens(text: str) -> set[str]:
    """Lower-case word tokens, minus stopwords, with a trailing plural 's' folded away."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in STOPWORDS}


def search(
    query: str, knowledge_base: tuple[Passage, ...], limit: int = MAX_RESULTS
) -> list[Passage]:
    """The best-matching passages for `query`, best first. Passages sharing no word are omitted.

    A word in the passage's title counts double. Ties break on id, so results are deterministic.
    """
    wanted = tokens(query)
    scored = []
    for passage in knowledge_base:
        in_title = tokens(passage.title)
        in_text = in_title | tokens(passage.text)
        score = sum((word in in_text) + (word in in_title) for word in wanted)
        if score:
            scored.append((-score, passage.id, passage))
    return [passage for _, _, passage in sorted(scored)[:limit]]


# --- Dependencies ---
@dataclass
class RagDeps:
    """Runtime dependencies for the retrieval agent."""

    # Swap in a vector store or search client here.
    knowledge_base: tuple[Passage, ...] = KNOWLEDGE_BASE
    # Ids of the passages retrieved during this run; citations are checked against it. A fresh
    # RagDeps per run (the default in run_rag) keeps one question's sources from leaking into the next.
    retrieved: set[str] = field(default_factory=set)


# --- Output type ---
class Answer(BaseModel):
    # `result` is the conventional output field in these examples; the generated
    # eval starter reads it when present (see evals/helpers.py).
    result: str
    sources: list[str] = []


# --- Agent ---
rag_agent: Agent[RagDeps, Answer] = Agent(
    settings.model,
    name=LABEL,
    output_type=Answer,
    deps_type=RagDeps,
    capabilities=[RaiseContentFilterError()],
    instructions=load_prompt("rag"),  # prompts/rag.txt; copied to agent/prompts/<name>.txt
)


# --- Tools ---
@rag_agent.tool
async def search_docs(ctx: RunContext[RagDeps], query: str) -> str:
    """Search the company documentation for passages relevant to a question or topic.

    Args:
        query: What to look for, in a few words (e.g. "boot return window").

    Returns:
        Up to three passages, each as `[id] Title: text`, best match first; or a note that nothing
        matched.

    Raises:
        ModelRetry: When the query is empty.
    """
    if not query.strip():
        raise ModelRetry("The query is empty. Search for a few specific words about the topic.")
    hits = search(query, ctx.deps.knowledge_base)
    logger.info("Search", extra={"query": query, "hits": [p.id for p in hits]})
    if not hits:
        return "No passages matched. Try different words, or tell the user you could not find it."
    ctx.deps.retrieved.update(p.id for p in hits)
    return "\n\n".join(f"[{p.id}] {p.title}: {p.text}" for p in hits)


# --- Grounding ---
@rag_agent.output_validator
def check_citations(ctx: RunContext[RagDeps], answer: Answer) -> Answer:
    """Reject a citation the model never retrieved; the message goes back to the model.

    This is what makes `sources` trustworthy: every id the user sees was in a search result.
    """
    invented = [source for source in answer.sources if source not in ctx.deps.retrieved]
    if invented:
        raise ModelRetry(
            f"You cited {invented}, which no search returned. Cite only passages returned by "
            "search_docs, or leave sources empty if nothing relevant was found."
        )
    return answer


async def run_rag(user_input: str, deps: RagDeps | None = None) -> RunResult[Answer]:
    """Answer `user_input` from the knowledge base.

    Returns:
        A RunResult: `.output` is the `Answer` (text and the ids it relies on); the searches the
        model made are in `.all_messages()`.
    """
    if deps is None:
        deps = RagDeps()
    logger.info("Running retrieval agent", extra={"user_input": user_input})
    flow = Flow(USAGE_LIMITS)
    result = await flow.run(rag_agent, user_input, deps=deps)
    return flow.finish(result.output)


if __name__ == "__main__":
    import asyncio

    configure_logging()
    print(asyncio.run(run_rag("How long do I have to return a pair of boots?")).output)
