# Sample run: Guardrails

*Recorded 2026-10-05 with `google:gemini-3.1-flash-lite` · 2 steps · 359 tokens · $0.0002 · 2.0 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py guardrails`.*

## Input

> How long should I boil an egg for a runny yolk?

## Steps

### 1. `guardrails.guard`
*210 tokens · $0.0001*

**Prompt**
> How long should I boil an egg for a runny yolk?

**Output**
```json
{
  "allowed": true,
  "reason": "I can certainly help you with the cooking time for a perfect runny egg yolk."
}
```

### 2. `guardrails.cooking`
*149 tokens · $0.0001*

**Prompt**
> How long should I boil an egg for a runny yolk?

**Output**
```json
{
  "result": "For a runny yolk with a just-set white, boil a large egg for **6 to 6.5 minutes**. \n\nImmediately place the egg in an ice water bath for 3 minutes after boiling to stop the cooking process and make it easier to peel."
}
```

## Result

`run_guarded(...).output`

```json
{
  "result": "For a runny yolk with a just-set white, boil a large egg for **6 to 6.5 minutes**. \n\nImmediately place the egg in an ice water bath for 3 minutes after boiling to stop the cooking process and make it easier to peel.",
  "blocked": false,
  "blocked_by": null
}
```
