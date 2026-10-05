# Sample run: Temporal

*Recorded 2026-10-05 with `google:gemini-3.1-flash-lite` · 1 step · 1,418 tokens · $0.0005 · 5.1 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py temporal`.*

## Input

> I'd like to order 3 gizmos for Norway. Are they in stock, and what is the shipping?

## Steps

### 1. `temporal`
*1,418 tokens · $0.0005*

**Prompt**
> I'd like to order 3 gizmos for Norway. Are they in stock, and what is the shipping?

**What happened**
- called `check_stock({"sku": "gizmo"})`
- `check_stock` returned: 8
- called `shipping_quote({"country": "Norway", "quantity": 3, "sku": "gizmo"})`
- `shipping_quote` returned: 20.3

**Output**
```json
{
  "result": "Yes, we have 3 gizmos in stock. The shipping cost to Norway for 3 gizmos is $20.30.",
  "shipping_usd": 20.3
}
```

## Result

`run_order_desk(...).output`

```json
{
  "result": "Yes, we have 3 gizmos in stock. The shipping cost to Norway for 3 gizmos is $20.30.",
  "shipping_usd": 20.3
}
```
