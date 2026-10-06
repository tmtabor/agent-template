"""The index, the vector search, the tool and the citation check, against a real Chroma server.

The tests that need the database run against the example's Docker service: the release check starts
it and passes its address in CHROMA_URL (see example.toml), and without it they are skipped. They
use a *scripted* embedder, which maps each text to a vector chosen by the test, so what is checked
is Chroma's real behaviour (cosine distance, ranking, counts, upserts) with exactly known inputs and
no embedding provider. Meaning-level quality of real embeddings is what test_live.py measures.
Needs chromadb-client (declared in example.toml), so the module is skipped without it.
"""

import math
import os
import uuid
from collections.abc import Sequence

import pytest

pytest.importorskip("chromadb", reason="needs chromadb-client")

from pydantic_ai import Embedder, ModelRetry, RunContext  # noqa: E402
from pydantic_ai.embeddings import EmbeddingModel, EmbeddingResult, TestEmbeddingModel  # noqa: E402
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart  # noqa: E402
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402
from pydantic_ai.usage import RequestUsage, RunUsage  # noqa: E402

from examples.rag import agent as module  # noqa: E402
from examples.rag.agent import (  # noqa: E402
    DEFAULT_EMBEDDING_MODELS,
    KNOWLEDGE_BASE,
    MAX_DISTANCE,
    MAX_RESULTS,
    Answer,
    ChromaUnavailable,
    EmbeddingModelNotConfigured,
    Passage,
    RagDeps,
    check_citations,
    chroma_url_from_env,
    connect,
    embedding_model,
    ensure_index,
    index_name,
    rag_agent,
    run_rag,
    search_docs,
    vector_search,
)

# --- A scripted embedder ---


def at(degrees: float) -> list[float]:
    """A unit vector at an angle: two such vectors are as far apart (cosine) as their angle says."""
    return [math.cos(math.radians(degrees)), math.sin(math.radians(degrees))]


def cosine_distance(a_degrees: float, b_degrees: float) -> float:
    return 1 - math.cos(math.radians(a_degrees - b_degrees))


class ScriptedEmbeddings(EmbeddingModel):
    """Embeds each text as the vector the test gave it, and counts how many texts it was asked for."""

    def __init__(self, vectors: dict[str, list[float]], name: str | None = None):
        super().__init__()
        self.vectors = vectors
        self.name = name or f"scripted-{uuid.uuid4().hex[:8]}"  # a fresh index per test
        self.texts_embedded = 0

    @property
    def model_name(self) -> str:
        return self.name

    @property
    def system(self) -> str:
        return "scripted"

    async def embed(
        self, inputs: str | Sequence[str], *, input_type, settings=None
    ) -> EmbeddingResult:
        texts, _ = self.prepare_embed(inputs, settings)
        self.texts_embedded += len(texts)
        return EmbeddingResult(
            embeddings=[self.vectors[text] for text in texts],
            inputs=texts,
            input_type=input_type,
            usage=RequestUsage(input_tokens=len(texts)),
            model_name=self.name,
            provider_name=self.system,
            provider_response_id=str(uuid.uuid4()),
        )

    async def max_input_tokens(self) -> int | None:
        return 1024

    async def count_tokens(self, text: str) -> int:
        return len(text.split())


def text_of(p: Passage) -> str:
    return f"{p.title}. {p.text}"  # what the agent embeds for a passage


# Three passages at 0, 30 and 90 degrees. A question at 10 degrees is 0.015 from the first, 0.060
# from the second and 0.826 from the third, which is beyond MAX_DISTANCE.
ALPHA = Passage("alpha", "Alpha", "The first passage.")
BETA = Passage("beta", "Beta", "The second passage.")
GAMMA = Passage("gamma", "Gamma", "The third passage.")
SMALL_KB = (ALPHA, BETA, GAMMA)
SMALL_VECTORS = {text_of(ALPHA): at(0), text_of(BETA): at(30), text_of(GAMMA): at(90)}


@pytest.fixture
def address() -> str:
    server = os.environ.get("CHROMA_URL")
    if not server:
        pytest.skip("needs the Chroma service running (CHROMA_URL)")
    return server


def make_deps(
    address: str, kb=SMALL_KB, vectors=None, questions=None
) -> tuple[RagDeps, ScriptedEmbeddings]:
    """Deps for a real Chroma and an embedder that knows the passages and the given questions."""
    model = ScriptedEmbeddings({**(vectors or SMALL_VECTORS), **(questions or {})})
    return RagDeps(knowledge_base=kb, chroma_url=address, embedder=Embedder(model)), model


def ctx(deps: RagDeps) -> RunContext[RagDeps]:
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage())


# --- Choosing and naming things, without the database ---


def test_the_index_is_named_after_the_documents_and_the_model():
    base = index_name("scripted:one", SMALL_KB)
    assert base == index_name("scripted:one", SMALL_KB)  # stable
    assert base.startswith("kb-") and 3 <= len(base) <= 512
    assert base != index_name("scripted:two", SMALL_KB)  # another model: vectors of another meaning
    changed = (ALPHA, Passage("beta", "Beta", "The second passage, edited."), GAMMA)
    assert base != index_name("scripted:one", changed)  # a passage was edited
    assert base != index_name("scripted:one", SMALL_KB[:2])  # a passage was removed


def test_an_embedding_model_can_be_chosen_in_the_environment(monkeypatch):
    monkeypatch.setenv("AGENT_EMBEDDING_MODEL", "openai:text-embedding-3-large")
    assert embedding_model() == "openai:text-embedding-3-large"


@pytest.mark.parametrize(
    ("llm", "expected"),
    [
        ("google:gemini-3.1-flash-lite", "google:gemini-embedding-001"),
        ("google-gla:gemini-3-pro", "google:gemini-embedding-001"),
        ("openai:gpt-5.2", "openai:text-embedding-3-small"),
    ],
)
def test_the_embedding_model_follows_the_llm_provider(monkeypatch, llm, expected):
    monkeypatch.delenv("AGENT_EMBEDDING_MODEL", raising=False)
    monkeypatch.setattr(module.settings, "model", llm)
    assert embedding_model() == expected
    assert expected in DEFAULT_EMBEDDING_MODELS.values()


def test_the_offline_test_model_gets_the_offline_embedding_model(monkeypatch):
    monkeypatch.delenv("AGENT_EMBEDDING_MODEL", raising=False)
    monkeypatch.setattr(module.settings, "model", "test")
    assert isinstance(embedding_model(), TestEmbeddingModel)


def test_a_provider_without_embeddings_asks_you_to_choose_one(monkeypatch):
    monkeypatch.delenv("AGENT_EMBEDDING_MODEL", raising=False)
    monkeypatch.setattr(module.settings, "model", "anthropic:claude-sonnet-5-5")
    with pytest.raises(EmbeddingModelNotConfigured, match="AGENT_EMBEDDING_MODEL"):
        embedding_model()


def test_the_database_address_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("CHROMA_URL", "http://chroma.internal:9000")
    assert chroma_url_from_env() == "http://chroma.internal:9000"
    assert RagDeps().chroma_url == "http://chroma.internal:9000"
    monkeypatch.delenv("CHROMA_URL")
    assert chroma_url_from_env() == module.DEFAULT_CHROMA_URL


def test_an_unreachable_database_is_reported_with_how_to_start_it():
    with pytest.raises(ChromaUnavailable, match="docker compose"):
        connect("http://127.0.0.1:1")


def test_a_secure_address_uses_tls_and_the_default_port(monkeypatch):
    seen = {}

    class Recording:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def heartbeat(self):
            return 1

    monkeypatch.setattr(module.chromadb, "HttpClient", Recording)
    connect("https://chroma.example.com")
    assert seen == {"host": "chroma.example.com", "port": 443, "ssl": True}
    connect("http://chroma.example.com")
    assert seen == {"host": "chroma.example.com", "port": 8000, "ssl": False}


def test_a_failure_that_is_not_a_connection_problem_is_not_disguised(monkeypatch):
    def broken(**kwargs):
        raise ValueError("the tenant does not exist")

    monkeypatch.setattr(module.chromadb, "HttpClient", broken)
    with pytest.raises(ValueError, match="tenant"):
        connect("http://127.0.0.1:8000")


async def test_a_run_fails_before_any_model_call_when_the_database_is_down():
    def must_not_run(messages, info):
        raise AssertionError("the model was called although there is no database")

    deps = RagDeps(chroma_url="http://127.0.0.1:1", embedder=Embedder(ScriptedEmbeddings({})))
    with rag_agent.override(model=FunctionModel(must_not_run)), pytest.raises(ChromaUnavailable):
        await run_rag("anything", deps)


# --- The index, in a real Chroma ---


async def test_the_index_holds_every_passage_with_its_text_and_title(address):
    deps, model = make_deps(address)
    collection = await ensure_index(deps)

    stored = collection.get(ids=["alpha", "beta", "gamma"], include=["documents", "metadatas"])
    assert dict(zip(stored["ids"], stored["documents"], strict=True)) == {
        "alpha": "The first passage.",
        "beta": "The second passage.",
        "gamma": "The third passage.",
    }
    assert {m["title"] for m in stored["metadatas"]} == {"Alpha", "Beta", "Gamma"}
    assert collection.count() == 3
    assert model.texts_embedded == 3
    assert collection.configuration_json["hnsw"]["space"] == "cosine"


async def test_an_index_that_is_already_complete_is_used_not_rebuilt(address):
    first, model = make_deps(address)
    await ensure_index(first)
    assert model.texts_embedded == 3

    # A second run with the same documents and model finds the collection full: no embedding calls.
    second = RagDeps(knowledge_base=SMALL_KB, chroma_url=address, embedder=Embedder(model))
    await ensure_index(second)
    assert model.texts_embedded == 3
    assert second.collection.name == first.collection.name


async def test_the_index_is_looked_up_once_per_run(address):
    deps, model = make_deps(address)
    first = await ensure_index(deps)
    assert (
        await ensure_index(deps) is first
    )  # cached on deps: no second lookup, no second embedding
    assert model.texts_embedded == 3


async def test_a_partly_built_index_is_completed(address):
    deps, model = make_deps(address)
    collection = await ensure_index(deps)
    collection.delete(ids=["gamma"])  # e.g. an earlier run that stopped part way
    assert collection.count() == 2

    again = RagDeps(knowledge_base=SMALL_KB, chroma_url=address, embedder=Embedder(model))
    await ensure_index(again)
    assert again.collection.count() == 3


async def test_a_different_embedding_model_gets_its_own_index(address):
    first, model_one = make_deps(address)
    second, model_two = make_deps(address)  # a different model name, so a different collection
    assert (await ensure_index(first)).name != (await ensure_index(second)).name
    assert model_one.texts_embedded == model_two.texts_embedded == 3


async def test_a_connection_is_made_from_the_address_when_no_client_is_given(address):
    deps, _ = make_deps(address)
    assert deps.client is None
    await ensure_index(deps)
    assert deps.client is not None


# --- Searching the index ---


async def test_the_nearest_passages_come_first_with_their_distances(address):
    deps, _ = make_deps(address, questions={"q": at(10)})
    hits = await vector_search(deps, "q")

    assert [h.id for h in hits] == ["alpha", "beta"]  # nearest first; gamma is too far to return
    assert hits[0].distance == pytest.approx(cosine_distance(10, 0), abs=1e-4)
    assert hits[1].distance == pytest.approx(cosine_distance(10, 30), abs=1e-4)
    assert (hits[0].title, hits[0].text) == ("Alpha", "The first passage.")


async def test_a_passage_beyond_the_maximum_distance_is_dropped(address):
    assert (
        cosine_distance(10, 90) > MAX_DISTANCE > cosine_distance(10, 30)
    )  # the setup is as described
    deps, _ = make_deps(address, questions={"far": at(180), "near": at(10)})
    assert await vector_search(deps, "far") == []  # opposite direction: nothing is near enough
    assert "gamma" not in [h.id for h in await vector_search(deps, "near", limit=3)]


async def test_the_number_of_results_is_limited(address):
    deps, _ = make_deps(address, questions={"q": at(10)})
    assert [h.id for h in await vector_search(deps, "q", limit=1)] == ["alpha"]
    assert MAX_RESULTS == 3


# --- The tool ---


async def test_a_search_returns_labelled_passages_and_records_what_was_retrieved(address):
    deps, _ = make_deps(address, questions={"q": at(10)})
    text = await search_docs(ctx(deps), "q")

    assert text == "[alpha] Alpha: The first passage.\n\n[beta] Beta: The second passage."
    assert deps.retrieved == {"alpha", "beta"}


async def test_a_search_with_nothing_near_says_so_and_records_nothing(address):
    deps, _ = make_deps(address, questions={"q": at(180)})
    text = await search_docs(ctx(deps), "q")
    assert text.startswith("No relevant passages found")
    assert deps.retrieved == set()


async def test_an_empty_query_asks_the_model_to_retry():
    with pytest.raises(ModelRetry, match="query is empty"):
        await search_docs(ctx(RagDeps()), "   ")


# --- The citation check ---


def test_citing_what_was_retrieved_is_accepted():
    deps = RagDeps(retrieved={"returns-policy"})
    answer = Answer(result="45 days", sources=["returns-policy"])
    assert check_citations(ctx(deps), answer) is answer


def test_no_sources_is_accepted():
    answer = Answer(result="I could not find that.", sources=[])
    assert check_citations(ctx(RagDeps()), answer) is answer


def test_citing_something_never_retrieved_is_rejected_with_the_offending_id():
    deps = RagDeps(retrieved={"returns-policy"})
    with pytest.raises(ModelRetry, match="invented-id"):
        check_citations(ctx(deps), Answer(result="x", sources=["returns-policy", "invented-id"]))


# --- Through the agent loop, with a scripted model ---


def scripted(*steps: dict):
    """A model that follows `steps`: a tool call ({"tool": ..., "args": ...}) or the final output."""
    remaining = list(steps)

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        step = remaining.pop(0)
        if "tool" in step:
            return ModelResponse(parts=[ToolCallPart(step["tool"], step["args"])])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, step["output"])])

    return FunctionModel(model_fn)


async def test_the_model_searches_then_answers_with_a_grounded_citation(address):
    deps, _ = make_deps(address, questions={"q": at(10)})
    model = scripted(
        {"tool": "search_docs", "args": {"query": "q"}},
        {"output": {"result": "It is the first.", "sources": ["alpha"]}},
    )
    with rag_agent.override(model=model):
        result = await run_rag("which?", deps)
    assert result.output.sources == ["alpha"]
    assert [step.agent for step in result.steps] == ["rag"]


async def test_an_ungrounded_citation_is_sent_back_and_the_model_corrects_it(address):
    deps, _ = make_deps(address, questions={"q": at(10)})
    model = scripted(
        {"tool": "search_docs", "args": {"query": "q"}},
        {"output": {"result": "It is the first.", "sources": ["made-up"]}},
        {"output": {"result": "It is the first.", "sources": ["alpha"]}},
    )
    with rag_agent.override(model=model):
        result = await run_rag("which?", deps)

    retries = [p for m in result.all_messages() for p in m.parts if isinstance(p, RetryPromptPart)]
    assert len(retries) == 1 and "made-up" in str(retries[0].content)
    assert result.output.sources == ["alpha"]


async def test_each_run_starts_with_nothing_retrieved(address):
    """Sources from one question must not make a citation valid in the next."""
    first_deps, model = make_deps(address, questions={"q": at(10)})
    first = scripted(
        {"tool": "search_docs", "args": {"query": "q"}},
        {"output": {"result": "a", "sources": ["alpha"]}},
    )
    with rag_agent.override(model=first):
        await run_rag("one", first_deps)

    second_deps = RagDeps(knowledge_base=SMALL_KB, chroma_url=address, embedder=Embedder(model))
    cites_without_searching = scripted(
        {"output": {"result": "b", "sources": ["alpha"]}},
        {"output": {"result": "b", "sources": []}},
    )
    with rag_agent.override(model=cites_without_searching):
        result = await run_rag("two", second_deps)
    assert result.output.sources == []  # the first attempt was rejected: nothing was retrieved yet


def test_the_real_knowledge_base_has_unique_ids_and_the_two_notices_differ_only_in_their_codes():
    ids = [p.id for p in KNOWLEDGE_BASE]
    assert len(ids) == len(set(ids))
    by_id = {p.id: p for p in KNOWLEDGE_BASE}
    assert "RN-2291" in by_id["recall-rn-2291"].text and "RN-2290" in by_id["recall-rn-2290"].text
