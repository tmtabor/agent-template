# Evaluator–optimizer

A generator drafts, a critic reviews against criteria, and they loop until the draft passes.

Two agents work in a loop. A generator writes a draft. A critic reviews it against criteria you wrote and either accepts it or returns specific feedback, and the feedback goes back to the generator for another try. The loop ends when the critic accepts or a round cap is reached; hitting the cap returns the last draft marked as not accepted, so the caller decides what to do. It trades extra model calls for a better answer, and how good the answer gets depends on how well you can state what good looks like.

**Use it when**

- You can state what "good" looks like as criteria a second model can check.
- A first attempt is usually close but benefits from targeted revision.
- A few extra model calls are worth a better answer.

**Look elsewhere when**

- "Good" can't be written down, or is better checked in code: a validator ([`extraction`](../extraction/)) is cheaper.
- A first attempt is usually fine: [`single`](../single/).

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

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

```bash
uv run python scripts/add_agent.py evaluator_optimizer --name descriptions
```

`run_evaluator_optimizer` returns a `RunResult`: `.output` carries `accepted` and `iterations`,
and `.steps` holds every generate and critique round in order.

Adapt it by rewriting the critic's criteria, which are the whole point.
`examples/evaluator_optimizer/test_example.py` tests the loop, the feedback and the cap.
