# Guardrails

Check what goes in and what comes out, and turn failures into safe answers.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

**Use it when** some requests should never reach the main agent (off-topic, unsafe, containing
private data), the agent's answer must not contain certain things whatever the model decides, and a
provider's content filter or an exhausted budget should degrade gracefully instead of crashing the
caller.

```
request → code guard ── card or ID number ──▶ refused (no model called)
              ▼
          topic guard ── off-topic or attack ─▶ refused (one small call)
              ▼
        cooking agent ── output validator ────▶ rewritten if it has personal data
              ▼
           answer     (provider filter or spent budget → a blocked answer)
```

**What it shows**

- **Cheapest layer first.** A regex check with a Luhn checksum refuses card and social security
  numbers *in code, before any model is called*, so the number never leaves your process and costs
  nothing. A random long number isn't mistaken for a card
- **A model guard** (`topic_guard_agent`) decides whether a request is on topic. It also catches
  attempts to change the assistant's instructions. A refused request never reaches the main agent,
  so it costs only the guard's small run; the spans prove the main agent didn't run
- **An output validator that doesn't trust the prompt.** The cooking prompt says nothing about
  personal data; the validator rejects any answer with an email, phone or card number and sends it
  back to be rewritten, so the guarantee holds even when the user asks the model to include one
- **Failures become answers.** `run_guarded` catches the provider's `ContentFilterError` and
  `UsageLimitExceeded` and returns a `GuardedAnswer` saying which layer blocked the request
  (`blocked_by`), rather than raising into the caller. Anything else still raises, so real bugs
  aren't hidden
- The result's `steps` show what ran: nothing if the code guard stopped it, only the guard if the
  model guard did, both agents otherwise

```bash
uv run python scripts/add_agent.py guardrails --name safe_assistant
```

To adapt it, replace the topic (the guard prompt and the cooking agent) and the patterns in
`find_sensitive_input` / `find_personal_data_in_output` with what your application must never accept
or emit. Keep the order: cheapest check first.
