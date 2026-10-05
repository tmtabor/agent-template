# Sample run: Router

*Recorded 2026-10-05 with `google:gemini-3.1-flash-lite` · 2 steps · 347 tokens · $0.0003 · 2.3 s.*
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
*206 tokens · $0.0002*

**Prompt**
> I was charged twice for my subscription this month.

**Output**
```json
{
  "result": "I am sorry to hear that you were charged twice for your subscription. I can certainly help you look into this.\n\nTo investigate this billing discrepancy, please provide the following information:\n\n1.  **The email address associated with your account.**\n2.  **The date(s) of the charges.**\n3.  **The amounts charged.**\n4.  **The last four digits of the payment method used** (please do not provide your full credit card number).\n\nOnce I have these details, I will be able to review your transaction history and process a refund for the duplicate charge if applicable."
}
```

## Result

`run_router(...).output`

```json
{
  "result": "I am sorry to hear that you were charged twice for your subscription. I can certainly help you look into this.\n\nTo investigate this billing discrepancy, please provide the following information:\n\n1.  **The email address associated with your account.**\n2.  **The date(s) of the charges.**\n3.  **The amounts charged.**\n4.  **The last four digits of the payment method used** (please do not provide your full credit card number).\n\nOnce I have these details, I will be able to review your transaction history and process a refund for the duplicate charge if applicable.",
  "category": "billing"
}
```
