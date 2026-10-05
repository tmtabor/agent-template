# Sample run: Retrieval (RAG)

*Recorded 2026-10-05 with `google:gemini-3.1-flash-lite` · 1 step · 865 tokens · $0.0003 · 1.6 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py rag`.*

## Input

> How long do I have to return a pair of boots?

## Steps

### 1. `rag`
*865 tokens · $0.0003*

**Prompt**
> How long do I have to return a pair of boots?

**What happened**
- called `search_docs({"query": "return policy boots"})`
- `search_docs` returned: [returns-policy] Returns: Unworn items can be returned within 45 days of delivery for a full refund. Boots must be returned in their original box. Sale items are final sale and cannot be returned. [wa …

**Output**
```json
{
  "result": "You have 45 days from the date of delivery to return unworn boots, provided they are in their original box. Note that sale items are final sale and cannot be returned.",
  "sources": [
    "returns-policy"
  ]
}
```

## Result

`run_rag(...).output`

```json
{
  "result": "You have 45 days from the date of delivery to return unworn boots, provided they are in their original box. Note that sale items are final sale and cannot be returned.",
  "sources": [
    "returns-policy"
  ]
}
```
