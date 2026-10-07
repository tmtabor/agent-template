# Sample run: Temporal

*Recorded 2026-10-07 with `google:gemini-3.1-flash-lite` · 1 step · 1,413 tokens · $0.0005 · 4.4 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py temporal`.*

## Input

> I'd like to order 3 gizmos for Norway. Are they in stock, and what is the shipping?

## Steps

### 1. `temporal`
*1,413 tokens · $0.0005*

**Prompt**
> I'd like to order 3 gizmos for Norway. Are they in stock, and what is the shipping?

**What happened**
- called `check_stock({"sku": "gizmo"})`
- `check_stock` returned: 8
- called `shipping_quote({"quantity": 3, "country": "Norway", "sku": "gizmo"})`
- `shipping_quote` returned: 20.3

**Output**
```json
{
  "result": "Yes, 3 gizmos are in stock, and the shipping cost to Norway is $20.30.",
  "shipping_usd": 20.3
}
```

## Result

`run_order_desk(...).output`

```json
{
  "result": "Yes, 3 gizmos are in stock, and the shipping cost to Norway is $20.30.",
  "shipping_usd": 20.3
}
```
