# Structured extraction

Turn unstructured text into a validated schema, and send the model back to fix what doesn't validate.

Extraction asks the model to fill in a typed record from free text: an email, a ticket, a document. Pydantic checks the shape, and an output validator you write checks the content. When either check fails, the reason goes back to the model in plain English and it tries again, up to a retry budget you set; when the budget runs out, the run raises instead of returning something half-valid. The result is data you can pass downstream without checking it again.

**Use it when**

- The input is free text (emails, tickets, documents) and you need typed fields out of it.
- Wrong output should be caught and corrected, not passed on.
- You can say, in code, what a valid answer looks like.

**Look elsewhere when**

- The output is prose for a person to read: [`single`](../single/) is enough.
- The schema is large or deeply nested: split the job (see [`pipeline`](../pipeline/)), because nesting the data doesn't need makes smaller models fail.

**What it shows**
- A flat output schema (`Contact`); nesting the data doesn't need makes smaller models fail
- An **output validator** that raises `ModelRetry` with a plain-English reason, so the model
  gets to fix its own answer
- An explicit retry budget (`retries={"output": 2}`); when it runs out the run raises
  `UnexpectedModelBehavior` instead of returning something half-valid
- `[smoke.extraction_agent]` in `example.toml`: `TestModel` generates junk that a real validator
  rejects, so the offline tests are told what to return

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

```bash
uv run python scripts/add_agent.py extraction --name contacts
```

Adapt it by replacing `Contact` with your schema and `check_contact` with your own checks.
