# Evaluator–optimizer

A generator drafts, a critic reviews against criteria, and they loop until the draft passes.

**Use it when** you can state what "good" looks like as criteria a second model can check, a
first attempt is usually close but benefits from targeted revision, and a few extra model
calls are worth a better answer.

```
generator → draft → critic ─ accepted ─→ done
     ▲                │
     └── feedback ────┘     (at most MAX_ITERATIONS rounds)
```

**What it shows**
- Two agents with a structured `Critique` (`accepted`, `feedback`) closing the loop
- A **round cap** (`MAX_ITERATIONS`) on top of `USAGE_LIMITS`; hitting it returns the last draft
  with `accepted=False` instead of looping or raising, so the caller decides
- Two prompt files, `evaluator_optimizer_generator.txt` and `evaluator_optimizer_critic.txt`
  (`add_agent.py` renames both to your agent's name)
- One `RunUsage` shared across rounds; trace labels `<name>.generator` and `<name>.critic`

```bash
uv run python scripts/add_agent.py evaluator_optimizer --name descriptions
```

`run_evaluator_optimizer` returns a `RunResult`: `.output` carries `accepted` and `iterations`,
and `.steps` holds every generate and critique round in order.

Adapt it by rewriting the critic's criteria, which are the whole point.
`examples/evaluator_optimizer/test_example.py` tests the loop, the feedback and the cap.
