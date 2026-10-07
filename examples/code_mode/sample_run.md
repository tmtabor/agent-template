# Sample run: Code mode

*Recorded 2026-10-07 with `google:gemini-3.1-flash-lite` · 1 step · 3,083 tokens · $0.0012 · 2.5 s.*
*Model output varies between runs. Regenerate with `uv run python scripts/record_example.py code_mode`.*

## Input

> What is the total of Maya's travel expenses, in US dollars?

## Steps

### 1. `code_mode`
*3,083 tokens · $0.0012*

**Prompt**
> What is the total of Maya's travel expenses, in US dollars?

**What happened**
- ran this code in the sandbox:

    ```python
    async def get_maya_travel_total():
        employees = await list_employees()
        maya_id = None
        for emp in employees:
            if emp['name'] == 'Maya':
                maya_id = emp['id']
                break
        
        if not maya_id:
            return "Maya not found"
        
        total_usd = 0.0
        expense_ids = await list_expense_ids(employee_id=maya_id)
        
        for exp_id in expense_ids:
            expense = await get_expense(expense_id=exp_id)
            if expense['category'] == 'travel':
                amount = expense['amount']
                currency = expense['currency']
                if currency == 'USD':
                    rate = 1.0
                else:
                    rate = await get_exchange_rate(currency=currency)
                total_usd += amount * rate
                
        return {"total": round(total_usd, 2), "id": maya_id}

    await get_maya_travel_total()
    ```
- `run_code` returned: {"total": 1520.12, "id": "E2"}

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
