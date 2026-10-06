"""Live check: real embeddings in a real Chroma service, and a real model answering from what it finds.

`-m eval`. The release check (scripts/release_check.py) builds and starts the Chroma service, then runs
this with its address in CHROMA_URL. To run it by hand: start the service, then set the variable:

    docker compose -f examples/rag/service/docker-compose.yml up -d --wait
    export CHROMA_URL=http://$(docker compose -f examples/rag/service/docker-compose.yml port chroma 8000)

The first half measures *retrieval* alone against a keyword baseline: that is why this example uses
vectors. The second half checks the whole agent.
"""

import os
import re

import pytest

pytest.importorskip("chromadb", reason="needs chromadb-client")

from evals.trace import traced_run  # noqa: E402
from examples.live_support import assert_every_agent_ran, run_as_script  # noqa: E402
from examples.rag import agent as module  # noqa: E402
from examples.rag.agent import KNOWLEDGE_BASE, MAX_DISTANCE, RagDeps, vector_search  # noqa: E402

pytestmark = pytest.mark.eval

if not os.environ.get("CHROMA_URL"):
    pytest.skip("needs the Chroma service running (CHROMA_URL)", allow_module_level=True)


# --- The baseline: what this example used before it had a vector database ---

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
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in STOPWORDS}


def keyword_ids(query: str) -> list[str]:
    """Passage ids by keyword overlap (a title word counts double), best first; none if no word is shared."""
    wanted = tokens(query)
    scored = []
    for passage in KNOWLEDGE_BASE:
        in_title = tokens(passage.title)
        in_text = in_title | tokens(passage.text)
        score = sum((word in in_text) + (word in in_title) for word in wanted)
        if score:
            scored.append((-score, passage.id))
    return [pid for _, pid in sorted(scored)]


# Questions in a customer's words, each with the passage that answers it. A mix: paraphrases that share
# no word with the answer, ones that do, and ones built on codes.
CASES = [
    ("How long can I send my hiking footwear back for my money?", "returns-policy"),
    ("Is there a charge to get a package delivered quickly?", "express-shipping"),
    ("Do you fix broken zippers?", "repairs"),
    ("Can I pay with a gift card instead of cash?", "gift-cards"),
    ("My boots fell apart after two years, am I covered?", "warranty-boots"),
    ("When can I visit the Portland shop on weekends?", "store-hours"),
    ("Will you match a lower price from another shop?", "price-match"),
    ("What perks do rewards members get?", "loyalty"),
    ("Does my backpack zipper have a guarantee?", "warranty-packs"),
    ("Can I send back something I bought on clearance?", "returns-policy"),
    ("What does recall notice RN-2291 cover?", "recall-rn-2291"),
    ("Is lot 4C-087 affected?", "recall-rn-2290"),
    ("RN-2290", "recall-rn-2290"),
    ("Which gloves were recalled?", "recall-rn-2290"),
    ("How long do I have to return boots?", "returns-policy"),
]
UNRELATED = [
    "What is the capital of France?",
    "How do I bake sourdough bread?",
    "Who won the world cup in 2018?",
]


@pytest.fixture(scope="module")
async def retrieval():
    """For every question, what the vector search returned (in order) and what the baseline did."""
    deps = RagDeps()
    return {
        question: ([h.id for h in await vector_search(deps, question)], keyword_ids(question))
        for question, _ in CASES
    }


async def test_the_right_passage_is_nearly_always_first(retrieval):
    first = sum(1 for question, want in CASES if retrieval[question][0][:1] == [want])
    assert first >= len(CASES) - 1  # measured: all 15 with Gemini embeddings; one miss of slack


async def test_the_right_passage_is_never_lost_to_the_distance_cutoff(retrieval):
    """MAX_DISTANCE must keep what is relevant: the right passage is among the results for every question."""
    missing = [q for q, want in CASES if want not in retrieval[q][0]]
    assert missing == []


async def test_vector_search_finds_what_the_keyword_baseline_misses(retrieval):
    vector_first = sum(1 for q, want in CASES if retrieval[q][0][:1] == [want])
    keyword_first = sum(1 for q, want in CASES if retrieval[q][1][:1] == [want])
    assert vector_first >= keyword_first + 3  # measured: 15 against 12

    paraphrase = "How long can I send my hiking footwear back for my money?"
    assert (
        retrieval[paraphrase][1] == []
    )  # no word in common with the policy: the baseline finds nothing
    assert retrieval[paraphrase][0][0] == "returns-policy"  # the vector search finds it first


async def test_a_question_that_is_one_passages_word_for_word_still_works(retrieval):
    """Meaning is not at the cost of an exact code: the two near-identical notices are told apart."""
    assert retrieval["What does recall notice RN-2291 cover?"][0][0] == "recall-rn-2291"
    assert retrieval["Is lot 4C-087 affected?"][0][0] == "recall-rn-2290"


async def distances(question: str) -> dict[str, float]:
    """The distance from the question to every passage in the index."""
    deps = RagDeps()
    collection = await module.ensure_index(deps)
    embedded = await deps.embedder.embed_query(question)
    found = collection.query(
        query_embeddings=[list(embedded.embeddings[0])], n_results=len(KNOWLEDGE_BASE)
    )
    return dict(zip(found["ids"][0], found["distances"][0], strict=True))


async def test_questions_with_no_connection_to_the_documents_return_nothing():
    deps = RagDeps()
    for question in UNRELATED:
        assert await vector_search(deps, question) == [], question


async def test_the_cutoff_sits_clear_of_both_the_right_passages_and_the_unrelated_questions():
    """If this fails after a change of embedding model, MAX_DISTANCE needs re-measuring."""
    right = max([(await distances(q))[want] for q, want in CASES])
    unrelated = min([min((await distances(q)).values()) for q in UNRELATED])
    margin = 0.03
    assert right + margin < MAX_DISTANCE < unrelated - margin, (right, MAX_DISTANCE, unrelated)


# --- The agent, end to end ---


async def ask(question: str):
    async def helper(text: str):
        return await module.run_rag(text)

    return await traced_run(helper, question)


@pytest.fixture(scope="module")
async def returns():
    return await ask("How long can I send my hiking footwear back for my money?")


@pytest.fixture(scope="module")
async def two_topics():
    return await ask("Is shipping free on a $60 order, and how long is the boot warranty?")


@pytest.fixture(scope="module")
async def recall():
    return await ask("What does recall notice RN-2291 cover, and what should I do?")


@pytest.fixture(scope="module")
async def not_covered():
    return await ask("Do you sell tents?")


async def test_a_question_in_the_customers_own_words_is_answered_with_its_source(returns):
    # "45 days" exists only in the invented policy, so it can't come from the model's memory, and the
    # question shares no word with the policy, so a keyword search could not have found it.
    assert "search_docs" in returns.tools_called
    output = returns.result.output
    assert "45" in output.result
    assert "returns-policy" in output.sources


async def test_a_two_part_question_draws_on_both_passages(two_topics):
    output = two_topics.result.output
    assert {"shipping-rates", "warranty-boots"} <= set(output.sources)
    answer = output.result.lower()
    # $60 is under the $75 free-shipping threshold, so it pays the $6.95 standard rate: a right answer
    # gives the rate or the threshold, whichever way it is worded.
    assert "6.95" in answer or "75" in answer
    assert "3" in answer and "year" in answer  # the 3-year boot warranty


async def test_a_question_about_one_code_is_not_answered_with_the_other_notice(recall):
    output = recall.result.output
    assert "recall-rn-2291" in output.sources
    assert "7B-114" in output.result
    assert "4C-087" not in output.result  # that is the other notice's lot


async def test_every_citation_is_a_passage_the_model_really_retrieved(returns, two_topics, recall):
    """The output validator enforces this; the message history shows the same thing independently."""
    for traced in (returns, two_topics, recall):
        seen = " ".join(
            str(part.content)
            for message in traced.result.all_messages()
            for part in message.parts
            if type(part).__name__ == "ToolReturnPart" and part.tool_name == "search_docs"
        )
        for source in traced.result.output.sources:
            assert f"[{source}]" in seen


async def test_a_question_the_documents_do_not_cover_cites_nothing(not_covered):
    """A vector search always returns the nearest passages, so the model must judge that none answers."""
    assert "search_docs" in not_covered.tools_called  # it looked
    assert not_covered.result.output.sources == []
    assert not_covered.result.output.result.strip()  # and it said something rather than nothing


async def test_the_agent_talks_to_the_service_docker_published():
    assert RagDeps().chroma_url == os.environ["CHROMA_URL"]
    assert RagDeps().chroma_url.startswith("http://127.0.0.1:")


async def test_the_agent_ran(returns, two_topics, recall, not_covered):
    ran = returns.agents_ran | two_topics.agents_ran | recall.agents_ran | not_covered.agents_ran
    assert_every_agent_ran(module, ran)


async def test_the_demo_script_runs():
    assert "returns-policy" in await run_as_script("examples.rag.agent")
