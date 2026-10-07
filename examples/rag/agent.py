"""Retrieval-augmented generation: answer from documents by meaning, and cite only what was retrieved.

Use this pattern when:
- Answers must come from your own documents, not the model's memory
- Users ask in their own words, not the documents' (so matching on keywords misses)
- Users need to see where an answer came from
- The model should say "I couldn't find that" rather than guess

How it works:
    1. Each passage is turned into an *embedding* (a vector that captures its meaning) and stored in
       a vector database, Chroma, which runs as its own service. This happens once per set of
       documents and embedding model (`ensure_index`)
    2. A retrieval tool (`search_docs`) embeds the question the same way and asks Chroma for the
       passages whose vectors are nearest, dropping any that are not near enough
    3. The model answers from those passages and lists their ids as `sources`
    4. An output validator rejects any source the model did not actually retrieve, so a citation
       can be trusted: it points at something the model really saw

"How long can I send my hiking footwear back for my money?" shares no word with the returns policy
("Unworn items can be returned within 45 days…"), so a keyword search finds nothing and a vector
search finds it first. The tests measure that against a keyword baseline.

Two things to know about vector search. It always returns the *nearest* passages, even when none
answers the question, so `MAX_DISTANCE` drops the clearly unrelated ones and the model is told to
answer only if a passage really contains the answer. And the embedding model is part of the index: a
different model makes vectors of a different size and meaning, so the index is named after both the
model and the documents, and a changed set of either is re-indexed into a new collection.

The policies are fictional on purpose: a model cannot answer from memory, so a correct answer proves
retrieval worked. Replace `KNOWLEDGE_BASE` with your own documents.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import chromadb
from pydantic import BaseModel
from pydantic_ai import Agent, Embedder, ModelRetry, RunContext
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.embeddings import TestEmbeddingModel
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
# A passage farther than this (cosine distance: 0 is identical, 1 is unrelated) is not returned. With
# Gemini embeddings the right passage was never farther than 0.31 across the 15 test questions, and
# questions with no connection to the documents were 0.43 or more away; this sits between the two.
# Distances are not comparable between embedding models, so re-measure when you change yours.
MAX_DISTANCE = 0.37

# Chroma's own port, for a server you start yourself on it. The Docker service publishes on a random free
# host port instead, so set CHROMA_URL to the address `docker compose port` shows (see service/).
DEFAULT_CHROMA_URL = "http://127.0.0.1:8000"
# The embedding model to use with each LLM provider's key, when AGENT_EMBEDDING_MODEL is not set.
# (Anthropic has no embedding model, so with an Anthropic LLM you must choose one yourself.)
DEFAULT_EMBEDDING_MODELS = {
    "google": "google:gemini-embedding-001",
    "google-gla": "google:gemini-embedding-001",
    "openai": "openai:text-embedding-3-small",
}


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
    Passage(
        "recall-rn-2291",
        "Recall notice RN-2291",
        "Recall notice RN-2291: Birchwood Ridgeline boots from production lot 7B-114 may have a "
        "loose heel counter. Stop wearing them and contact us for a free replacement pair. Other "
        "lots are not affected.",
    ),
    Passage(
        "recall-rn-2290",
        "Recall notice RN-2290",
        "Recall notice RN-2290: Birchwood Summit gloves from production lot 4C-087 may shed lining "
        "fibres. Stop using them and contact us for a refund. Other lots are not affected.",
    ),
)


# --- Embeddings and the vector database ---
class EmbeddingModelNotConfigured(Exception):
    """No embedding model is configured and none can be inferred from the LLM provider."""


class ChromaUnavailable(Exception):
    """The Chroma server could not be reached."""


def chroma_url_from_env() -> str:
    return os.environ.get("CHROMA_URL", DEFAULT_CHROMA_URL)


def embedding_model() -> Any:
    """The embedding model to use: AGENT_EMBEDDING_MODEL, else the one that goes with the LLM's provider.

    Under the offline test model (`AGENT_MODEL=test`) this is Pydantic AI's `TestEmbeddingModel`, so
    nothing calls a real provider, just as the agent itself does not.
    """
    configured = os.environ.get("AGENT_EMBEDDING_MODEL")
    if configured:
        return configured
    provider = settings.model.split(":")[0]
    if provider == "test":
        return TestEmbeddingModel()
    if provider in DEFAULT_EMBEDDING_MODELS:
        return DEFAULT_EMBEDDING_MODELS[provider]
    raise EmbeddingModelNotConfigured(
        f"No embedding model for the {provider!r} provider. Set AGENT_EMBEDDING_MODEL in .env, "
        "for example google:gemini-embedding-001 or openai:text-embedding-3-small."
    )


def connect(url: str) -> Any:
    """A client for the Chroma server at `url`, checked with a heartbeat."""
    parts = urlparse(url)
    secure = parts.scheme == "https"
    try:
        client = chromadb.HttpClient(
            host=parts.hostname or "127.0.0.1",
            port=parts.port or (443 if secure else 8000),
            ssl=secure,
        )
        client.heartbeat()
    except ValueError as exc:  # Chroma reports a refused connection as a ValueError
        if "connect" not in str(exc).lower():
            raise
        raise ChromaUnavailable(
            f"No Chroma server at {url}. Start the service (`docker compose up -d --wait` in the "
            "directory with its docker-compose.yml) and set CHROMA_URL to the address Docker "
            "published, or point CHROMA_URL at your own Chroma server."
        ) from exc
    return client


def index_name(embedding_model_id: str, knowledge_base: tuple[Passage, ...]) -> str:
    """The collection's name: a fingerprint of the embedding model and every passage.

    Changing either gives a new name, so a new collection is built; the old one is left alone.
    """
    digest = hashlib.sha256(embedding_model_id.encode())
    for p in knowledge_base:
        digest.update(f"\0{p.id}\0{p.title}\0{p.text}".encode())
    return f"kb-{digest.hexdigest()[:16]}"


# --- Dependencies ---
@dataclass
class RagDeps:
    """Runtime dependencies for the retrieval agent."""

    knowledge_base: tuple[Passage, ...] = KNOWLEDGE_BASE
    chroma_url: str = field(default_factory=chroma_url_from_env)
    # Ids of the passages retrieved during this run; citations are checked against it. A fresh
    # RagDeps per run (the default in run_rag) keeps one question's sources from leaking into the next.
    retrieved: set[str] = field(default_factory=set)
    # Normally left unset: built from the settings above on first use. Set them to use another
    # Chroma client or embedding model, such as an in-process client in tests.
    client: Any = None
    embedder: Embedder | None = None
    collection: Any = None  # the index; filled in by ensure_index


async def ensure_index(deps: RagDeps) -> Any:
    """The collection holding `deps.knowledge_base`'s embeddings, building it if it is not there yet.

    Safe to call on every run: a collection with all the passages is used as it is.
    """
    if deps.collection is not None:
        return deps.collection
    if deps.embedder is None:
        deps.embedder = Embedder(embedding_model())
    if deps.client is None:
        deps.client = await asyncio.to_thread(connect, deps.chroma_url)
    model = deps.embedder.model  # the name it was given, or the model instance
    model_id = model if isinstance(model, str) else f"{model.system}:{model.model_name}"
    name = index_name(model_id, deps.knowledge_base)
    collection = await asyncio.to_thread(
        deps.client.get_or_create_collection, name, configuration={"hnsw": {"space": "cosine"}}
    )
    if await asyncio.to_thread(collection.count) != len(deps.knowledge_base):
        # A passage is embedded with its title, which is part of what it is about.
        embedded = await deps.embedder.embed_documents(
            [f"{p.title}. {p.text}" for p in deps.knowledge_base]
        )
        await asyncio.to_thread(
            collection.upsert,
            ids=[p.id for p in deps.knowledge_base],
            documents=[p.text for p in deps.knowledge_base],
            metadatas=[{"title": p.title} for p in deps.knowledge_base],
            embeddings=[list(vector) for vector in embedded.embeddings],
        )
        logger.info(
            "Indexed passages", extra={"collection": name, "count": len(deps.knowledge_base)}
        )
    deps.collection = collection
    return collection


@dataclass(frozen=True)
class Hit:
    """A passage the search returned, and how far its vector is from the question's."""

    id: str
    title: str
    text: str
    distance: float


async def vector_search(deps: RagDeps, query: str, limit: int = MAX_RESULTS) -> list[Hit]:
    """The passages nearest in meaning to `query`, nearest first, none farther than MAX_DISTANCE."""
    collection = await ensure_index(deps)
    assert deps.embedder is not None  # ensure_index sets it
    embedded = await deps.embedder.embed_query(query)
    found = await asyncio.to_thread(
        collection.query,
        query_embeddings=[list(embedded.embeddings[0])],
        n_results=limit,
        include=["documents", "metadatas", "distances"],
    )
    return [
        Hit(id=pid, title=meta["title"], text=text, distance=distance)
        for pid, text, meta, distance in zip(
            found["ids"][0],
            found["documents"][0],
            found["metadatas"][0],
            found["distances"][0],
            strict=True,
        )
        if distance <= MAX_DISTANCE
    ]


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
        query: What to look for: the question itself or a short description of the topic.

    Returns:
        Up to three passages, each as `[id] Title: text`, nearest in meaning first; or a note that
        nothing relevant was found.

    Raises:
        ModelRetry: When the query is empty.
    """
    if not query.strip():
        raise ModelRetry(
            "The query is empty. Search for the question or a description of the topic."
        )
    hits = await vector_search(ctx.deps, query)
    logger.info(
        "Search", extra={"query": query, "hits": [(h.id, round(h.distance, 3)) for h in hits]}
    )
    if not hits:
        return "No relevant passages found. Rephrase the query, or tell the user you could not find it."
    ctx.deps.retrieved.update(hit.id for hit in hits)
    return "\n\n".join(f"[{hit.id}] {hit.title}: {hit.text}" for hit in hits)


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

    Raises:
        ChromaUnavailable: When the Chroma server can't be reached.
        EmbeddingModelNotConfigured: When no embedding model is set and none fits the LLM provider.
    """
    if deps is None:
        deps = RagDeps()
    logger.info("Running retrieval agent", extra={"user_input": user_input})
    await ensure_index(
        deps
    )  # fail before any model call if the database or embeddings are not usable
    flow = Flow(USAGE_LIMITS)
    result = await flow.run(rag_agent, user_input, deps=deps)
    return flow.finish(result.output)


if __name__ == "__main__":
    configure_logging()
    print(asyncio.run(run_rag("How long can I send my hiking footwear back for my money?")).output)
