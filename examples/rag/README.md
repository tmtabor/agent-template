# Retrieval (RAG)

Answer questions from your own documents, and let the user see where each answer came from.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

**Use it when** answers must come from your documents rather than the model's memory, users need
to see sources, and "I couldn't find that" is better than a guess.

```
question → search_docs → passages → answer + sources → citation check
```

**What it shows**

- A retrieval tool, `search_docs`, over an in-memory knowledge base of invented store policies,
  scored by keyword overlap. The policies are fictional on purpose: a model can't answer from
  memory, so a correct answer proves retrieval worked. Swap `search` for a vector store or search
  API; nothing else changes
- **Trustworthy citations:** an output validator rejects any source the model didn't actually
  retrieve (`RagDeps.retrieved` records every id a search returned), so each id the user sees was
  in a real search result
- **Saying no:** when nothing matches, the tool says so and the model leaves `sources` empty
  instead of guessing
- Retrieval state lives in deps, one fresh `RagDeps` per run, so one question's sources never leak
  into the next

```bash
uv run python scripts/add_agent.py rag --name support_docs
```

To adapt it, replace `KNOWLEDGE_BASE` and `search` with your own corpus and retrieval, and rewrite
`prompts/rag.txt` for your domain.
