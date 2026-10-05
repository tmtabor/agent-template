# Sample run: MCP tools

*Recorded 2026-10-05 with `google:gemini-3.1-flash-lite` · 1 step · 793 tokens · $0.0003 · 2.0 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py mcp_tools`.*

## Input

> How many days are there from 2024-02-10 to 2024-03-01?

## Steps

### 1. `mcp_tools`
*793 tokens · $0.0003*

**Prompt**
> How many days are there from 2024-02-10 to 2024-03-01?

**What happened**
- called `days_between({"start": "2024-02-10", "end": "2024-03-01"})`
- `days_between` returned: 20

**Output**
```json
{
  "result": "There are 20 days from 2024-02-10 to 2024-03-01."
}
```

## Result

`run_mcp(...).output`

```json
{
  "result": "There are 20 days from 2024-02-10 to 2024-03-01."
}
```
