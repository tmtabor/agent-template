# Sample run: Human in the loop

*Recorded 2026-10-05 with `google:gemini-3.1-flash-lite` · 2 steps · 1,628 tokens · $0.0009 · 2.5 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py human_in_the_loop`.*

## Input

> Order A100 arrived with a broken sole. Please refund the full $84.50.

## Steps

### 1. `human_in_the_loop`
*1,009 tokens · $0.0003*

**Prompt**
> Order A100 arrived with a broken sole. Please refund the full $84.50.

**What happened**
- called `lookup_order({"order_id": "A100"})`
- `lookup_order` returned: Order A100: Trailhead boots, total $84.50, status delivered.
- called `issue_refund({"order_id": "A100", "reason": "broken sole", "amount_usd": 84.5})`

**Output**
```text
The run paused: waiting for a decision on
  approve  issue_refund({"order_id": "A100", "reason": "broken sole", "amount_usd": 84.5})
```

### 2. `human_in_the_loop`
*1,628 tokens · $0.0005*

**Prompt**
> Order A100 arrived with a broken sole. Please refund the full $84.50.

**What happened**
- called `lookup_order({"order_id": "A100"})`
- `lookup_order` returned: Order A100: Trailhead boots, total $84.50, status delivered.
- called `issue_refund({"order_id": "A100", "reason": "broken sole", "amount_usd": 84.5})`
- `issue_refund` returned: No approver is configured, so this action was not approved.

**Output**
```json
{
  "result": "I am sorry, but your refund request for order A100 could not be processed as it requires a manual approval that is not currently available.",
  "refunded": false
}
```

## Result

`run_refunds(...).output`

```json
{
  "result": "I am sorry, but your refund request for order A100 could not be processed as it requires a manual approval that is not currently available.",
  "refunded": false
}
```
