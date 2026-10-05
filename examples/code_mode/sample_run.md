# Sample run: Code mode

*Recorded 2026-10-05 with `google:gemini-3.1-flash-lite` · 1 step · 2,952 tokens · $0.0010 · 2.9 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py code_mode`.*

## Input

> What is the total of Maya's travel expenses, in US dollars?

## Steps

### 1. `code_mode`
*2,952 tokens · $0.0010*

**Prompt**
> What is the total of Maya's travel expenses, in US dollars?

**What happened**
- ran this code in the sandbox:

    ```python
    employees = await list_employees()
    maya_id = None
    for emp in employees:
        if emp["name"] == "Maya":
            maya_id = emp["id"]
            break

    total_usd = 0.0
    if maya_id:
        expense_ids = await list_expense_ids(employee_id=maya_id)
        for exp_id in expense_ids:
            expense = await get_expense(expense_id=exp_id)
            if expense["category"] == "travel":
                amount = expense["amount"]
                currency = expense["currency"]
                rate = await get_exchange_rate(currency=currency)
                total_usd += amount * rate

    print(round(total_usd, 2))
    print(maya_id)
    ```
- `run_code` returned: {"output": "1520.12\nE2\n"}

**Output**
```json
{
  "result": "The total of Maya's travel expenses is $1520.12.",
  "amount_usd": 1520.12,
  "subject": "E2"
}
```

## Result

`run_expenses(...).output`

```json
{
  "result": "The total of Maya's travel expenses is $1520.12.",
  "amount_usd": 1520.12,
  "subject": "E2"
}
```
