# Sample run: Retrieval (RAG)

*Recorded 2026-10-07 with `google:gemini-3.1-flash-lite` · 1 step · 1,027 tokens · $0.0004 · 2.0 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py rag`.*

## Input

> How long can I send my hiking footwear back for my money?

## Steps

### 1. `rag`
*1,027 tokens · $0.0004*

**Prompt**
> How long can I send my hiking footwear back for my money?

**What happened**
- called `search_docs({"query": "return policy for hiking footwear refund time limit"})`
- `search_docs` returned: [returns-policy] Returns: Unworn items can be returned within 45 days of delivery for a full refund. Boots must be returned in their original box. Sale items are final sale and cannot be returned. [re …

**Output**
```json
{
  "result": "You can return unworn hiking footwear within 45 days of delivery for a full refund. Please note that the boots must be returned in their original box and that sale items are final sale.",
  "sources": [
    "returns-policy"
  ]
}
```

## Result

`run_rag(...).output`

```json
{
  "result": "You can return unworn hiking footwear within 45 days of delivery for a full refund. Please note that the boots must be returned in their original box and that sale items are final sale.",
  "sources": [
    "returns-policy"
  ]
}
```
