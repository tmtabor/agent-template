# Sample run: Structured extraction

*Recorded 2026-10-07 with `google:gemini-3.1-flash-lite` · 1 step · 222 tokens · $0.0001 · 1.2 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py extraction`.*

## Input

> Hi, it's Ada Lovelace from Analytical Engines Ltd. Reach me at ada@example.com.

## Steps

### 1. `extraction`
*222 tokens · $0.0001*

**Prompt**
> Hi, it's Ada Lovelace from Analytical Engines Ltd. Reach me at ada@example.com.

**Output**
```json
{
  "name": "Ada Lovelace",
  "email": "ada@example.com",
  "phone": null,
  "company": "Analytical Engines Ltd."
}
```

## Result

`run_extraction(...).output`

```json
{
  "name": "Ada Lovelace",
  "email": "ada@example.com",
  "phone": null,
  "company": "Analytical Engines Ltd."
}
```
