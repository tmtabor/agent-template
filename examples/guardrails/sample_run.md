# Sample run: Guardrails

*Recorded 2026-10-07 with `google:gemini-3.1-flash-lite` · 2 steps · 355 tokens · $0.0002 · 2.4 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py guardrails`.*

## Input

> How long should I boil an egg for a runny yolk?

## Steps

### 1. `guardrails.guard`
*211 tokens · $0.0001*

**Prompt**
> How long should I boil an egg for a runny yolk?

**Output**
```json
{
  "allowed": true,
  "reason": "I can provide you with the timing for boiling an egg to achieve a runny yolk."
}
```

### 2. `guardrails.cooking`
*144 tokens · $0.0001*

**Prompt**
> How long should I boil an egg for a runny yolk?

**Output**
```json
{
  "result": "To get a runny yolk, boil a large egg for **6 to 6 ½ minutes**. \n\nPlace the eggs into already boiling water, then immediately transfer them to an ice water bath once the time is up to stop the cooking process."
}
```

## Result

`run_guarded(...).output`

```json
{
  "result": "To get a runny yolk, boil a large egg for **6 to 6 ½ minutes**. \n\nPlace the eggs into already boiling water, then immediately transfer them to an ice water bath once the time is up to stop the cooking process.",
  "blocked": false,
  "blocked_by": null
}
```
