"""Retrieval, the search tool, and the citation check — each branch, offline."""

import pytest
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from examples.rag.agent import (
    KNOWLEDGE_BASE,
    MAX_RESULTS,
    Answer,
    Passage,
    RagDeps,
    check_citations,
    rag_agent,
    run_rag,
    search,
    search_docs,
    tokens,
)


def ctx(deps: RagDeps | None = None) -> RunContext[RagDeps]:
    return RunContext(deps=deps or RagDeps(), model=TestModel(), usage=RunUsage())


def ids(query: str, kb=KNOWLEDGE_BASE) -> list[str]:
    return [p.id for p in search(query, kb)]


# --- Retrieval ---


def test_tokens_drop_stopwords_and_fold_plurals():
    assert tokens("How long do I have to return the boots?") == {"long", "have", "return", "boot"}


def test_the_best_match_comes_first():
    assert ids("How long do I have to return a pair of boots?")[0] == "returns-policy"
    assert ids("boot warranty")[0] == "warranty-boots"


def test_a_title_match_outranks_a_text_only_match():
    kb = (
        Passage("in-text", "Other", "The word zipper appears only here."),
        Passage("in-title", "Zipper", "Something else entirely."),
    )
    assert ids("zipper", kb) == ["in-title", "in-text"]


def test_no_shared_word_means_no_passages():
    assert ids("Do you sell tents?") == []
    assert ids("") == []


def test_results_are_limited():
    assert (
        len(ids("shipping orders boots warranty store gift price loyalty repairs")) == MAX_RESULTS
    )


def test_ties_break_on_id_so_results_are_deterministic():
    kb = (Passage("b", "T", "alpha"), Passage("a", "T", "alpha"))
    assert ids("alpha", kb) == ["a", "b"]


# --- The tool ---


async def test_a_search_returns_labelled_passages_and_records_what_was_retrieved():
    deps = RagDeps()
    text = await search_docs(ctx(deps), "return window for boots")
    assert text.startswith("[returns-policy] Returns: Unworn items can be returned within 45 days")
    assert "returns-policy" in deps.retrieved
    assert deps.retrieved == {line.split("]")[0][1:] for line in text.split("\n\n")}


async def test_a_search_with_no_match_says_so_and_records_nothing():
    deps = RagDeps()
    text = await search_docs(ctx(deps), "tents")
    assert text.startswith("No passages matched")
    assert deps.retrieved == set()


async def test_an_empty_query_asks_the_model_to_retry():
    with pytest.raises(ModelRetry, match="query is empty"):
        await search_docs(ctx(), "   ")


async def test_the_knowledge_base_comes_from_deps():
    deps = RagDeps(knowledge_base=(Passage("only", "Only", "A single passage about zebras."),))
    assert (await search_docs(ctx(deps), "zebras")).startswith("[only]")


# --- The citation check ---


def test_citing_what_was_retrieved_is_accepted():
    deps = RagDeps(retrieved={"returns-policy"})
    answer = Answer(result="45 days", sources=["returns-policy"])
    assert check_citations(ctx(deps), answer) is answer


def test_no_sources_is_accepted():
    answer = Answer(result="I could not find that.", sources=[])
    assert check_citations(ctx(), answer) is answer


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


async def test_the_model_searches_then_answers_with_a_grounded_citation():
    model = scripted(
        {"tool": "search_docs", "args": {"query": "boot returns"}},
        {"output": {"result": "45 days.", "sources": ["returns-policy"]}},
    )
    with rag_agent.override(model=model):
        result = await run_rag("How long to return boots?")
    assert result.output.sources == ["returns-policy"]
    assert [step.agent for step in result.steps] == ["rag"]


async def test_an_ungrounded_citation_is_sent_back_and_the_model_corrects_it():
    model = scripted(
        {"tool": "search_docs", "args": {"query": "boot returns"}},
        {"output": {"result": "45 days.", "sources": ["made-up"]}},
        {"output": {"result": "45 days.", "sources": ["returns-policy"]}},
    )
    with rag_agent.override(model=model):
        result = await run_rag("How long to return boots?")

    retries = [p for m in result.all_messages() for p in m.parts if isinstance(p, RetryPromptPart)]
    assert len(retries) == 1 and "made-up" in str(retries[0].content)
    assert result.output.sources == ["returns-policy"]


async def test_each_run_starts_with_nothing_retrieved():
    """Sources from one question must not make a citation valid in the next."""
    first = scripted(
        {"tool": "search_docs", "args": {"query": "boot returns"}},
        {"output": {"result": "a", "sources": ["returns-policy"]}},
    )
    with rag_agent.override(model=first):
        await run_rag("one")

    cites_without_searching = scripted(
        {"output": {"result": "b", "sources": ["returns-policy"]}},
        {"output": {"result": "b", "sources": []}},
    )
    with rag_agent.override(model=cites_without_searching):
        result = await run_rag("two")
    assert result.output.sources == []  # the first attempt was rejected: nothing was retrieved yet
