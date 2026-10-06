# Retrieval (RAG)

Answer questions from your own documents, find them by meaning, and let the user see where each answer came from.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

**Use it when** answers must come from your documents rather than the model's memory, users ask in
their own words rather than the documents', users need to see sources, and "I couldn't find that" is
better than a guess.

```
documents ─ embed ─▶ Chroma (its own service)
                          ▲
question ─ embed ─▶ search_docs ─▶ nearest passages ─▶ answer + sources ─▶ citation check
```

**What it shows**

- **Search by meaning, in a real vector database.** Each passage is embedded (a vector that captures
  what it is about) and stored in Chroma, which runs as its own Docker service. `search_docs` embeds
  the question the same way and asks Chroma for the nearest passages. "How long can I send my hiking
  footwear back for my money?" shares no word with the returns policy, and finds it first
- **It is measured, not assumed.** `test_live.py` runs 15 questions against a keyword baseline with real
  embeddings: the right passage came first for **15 of 15** by vector search and **12 of 15** by keyword
  search (which found nothing for the paraphrase above, and the wrong passage for another)
- **An index you do not manage by hand.** `ensure_index` names the collection after the embedding model
  and a fingerprint of the documents, and fills it only if it is not full already. Edit a document or
  change the model and a new collection is built; the next run does nothing if it is already there
- **Nearest is not relevant.** A vector search always returns *something*. `MAX_DISTANCE` drops the
  clearly unrelated passages (the right one was never farther than 0.31 in the 15 test questions; unrelated
  questions were 0.43 or more away; `MAX_DISTANCE` is 0.37, between the two), and the prompt tells the model to answer only from a passage that really
  says it. "Do you sell tents?" returns the nearest passages and the model still says it could not find it
- **Trustworthy citations:** an output validator rejects any source the model didn't actually
  retrieve (`RagDeps.retrieved` records every id a search returned), so each id the user sees was
  in a real search result
- **The address is a dependency.** `RagDeps.chroma_url` (from `CHROMA_URL`) points the agent at the
  local service or a staging database; `ChromaUnavailable` says where it looked

## Why vectors and not both

The obvious next idea is a hybrid: run keyword and vector search and merge the rankings. We measured
it (reciprocal-rank fusion, with the vector side weighted 1x, 2x and 3x) and it did **worse** than
vectors alone on this set: 14 of 15 first, not 15. A single spurious keyword hit (a question about
"a charge to get a package delivered quickly" matched the Trail Club passage) outranked the right
vector answer however heavily the vector side was weighted. With a strong embedding model and a corpus
like this one, keyword search added noise. That can change with a weaker embedding model or a corpus
full of exact identifiers, so measure on yours; the keyword baseline in `test_live.py` is the starting
point for that comparison.

## Running it

```bash
docker compose -f examples/rag/service/docker-compose.yml up -d --wait
export CHROMA_URL=http://$(docker compose -f examples/rag/service/docker-compose.yml port chroma 8000)
uv run --with "chromadb-client>=1.5,<1.6" python -m examples.rag.agent
docker compose -f examples/rag/service/docker-compose.yml down
```

The embedding model follows your LLM's provider: Google or OpenAI work out of the box. Anthropic has no
embedding model, so with an Anthropic LLM set `AGENT_EMBEDDING_MODEL` in `.env` (for example
`google:gemini-embedding-001` or `openai:text-embedding-3-small`; the key for that provider must be set
too). The first run embeds the documents; later runs reuse them.

To use it in your project, `add_agent.py` copies the agent into `agent/agents/`, the service into
`services/<name>/`, and installs `chromadb-client`:

```bash
uv run python scripts/add_agent.py rag --name support_docs
```

To adapt it, replace `KNOWLEDGE_BASE` with your own documents (long ones should be split into passages
first) and rewrite `prompts/rag.txt` for your domain. Re-measure `MAX_DISTANCE` for your embedding
model: distances are not comparable between models.

## Notes

- **The tests use the real service.** Chroma's slim client and its full engine cannot be installed
  together (both provide the `chromadb` module), so there is no in-process Chroma for the offline
  tests. They run against the Docker service with a scripted embedder (each text maps to a vector the
  test chose, so distances are known exactly) and are skipped without `CHROMA_URL`. The live tests then
  use real embeddings
- **Old collections stay.** A new embedding model or edited documents create a new collection; the old
  one is left in the database. Delete it when you no longer need it
- **Pin the server to the client's version.** `service/docker-compose.yml` names `chromadb/chroma:1.5.9`
  to match `chromadb-client` 1.5; `latest` was a minor version behind the client when this was written
