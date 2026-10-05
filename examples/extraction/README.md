# Structured extraction

Turn unstructured text into a validated schema.

**Use it when** the input is free text (emails, tickets, documents) and you need typed
fields out, and bad output should be caught and corrected rather than passed downstream.

**What it shows**
- A flat output schema (`Contact`); nesting the data doesn't need makes smaller models fail
- An **output validator** that raises `ModelRetry` with a plain-English reason, so the model
  gets to fix its own answer
- An explicit retry budget (`retries={"output": 2}`); when it runs out the run raises
  `UnexpectedModelBehavior` instead of returning something half-valid
- `[smoke.extraction_agent]` in `example.toml`: `TestModel` generates junk that a real validator
  rejects, so the offline tests are told what to return

```bash
uv run python scripts/add_agent.py extraction --name contacts
```

Adapt it by replacing `Contact` with your schema and `check_contact` with your own checks.
