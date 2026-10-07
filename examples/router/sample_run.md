# Sample run: Router

*Recorded 2026-10-07 with `google:gemini-3.1-flash-lite` · 2 steps · 334 tokens · $0.0003 · 1.8 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py router`.*

## Input

> I was charged twice for my subscription this month.

## Steps

### 1. `router.classifier`
*141 tokens · $0.0001*

**Prompt**
> I was charged twice for my subscription this month.

**Output**
```json
{
  "category": "billing"
}
```

### 2. `router.billing`
*193 tokens · $0.0002*

**Prompt**
> I was charged twice for my subscription this month.

**Output**
```json
{
  "result": "I’m sorry to hear that you were charged twice. I can certainly help you look into this.\n\nTo get started, please provide the following information:\n\n1. The email address associated with your subscription account.\n2. The dates and amounts of the two separate charges.\n3. If you have them, the transaction IDs or order numbers for both charges.\n\nOnce I have those details, I will investigate the billing records and process a refund for the duplicate charge if confirmed. Please do not share any full credit card numbers or passwords here."
}
```

## Result

`run_router(...).output`

```json
{
  "result": "I’m sorry to hear that you were charged twice. I can certainly help you look into this.\n\nTo get started, please provide the following information:\n\n1. The email address associated with your subscription account.\n2. The dates and amounts of the two separate charges.\n3. If you have them, the transaction IDs or order numbers for both charges.\n\nOnce I have those details, I will investigate the billing records and process a refund for the duplicate charge if confirmed. Please do not share any full credit card numbers or passwords here.",
  "category": "billing"
}
```
