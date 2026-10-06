# Blank

The smallest agent the template supports: one output type, one prompt file, no tools.

Blank is a starting point, not a pattern. It is one agent module with a typed output model, a dependencies dataclass, a prompt in `agent/prompts/<name>.txt`, and a `run_*` function that returns a [`RunResult`](../../README.md#agents), wrapped in the template's guardrails: limits on requests and tokens, and an error when a provider blocks a response. Unlike the other examples, every symbol in it is renamed to the name you choose: `--name newsletter` gives you `newsletter_agent`, `NewsletterOutput`, `NewsletterDeps` and `run_newsletter_agent`. You also get a smoke test and an eval starter for it, as with any agent you add.

**Use it when**

- You know what you want to build and none of the patterns matches its shape yet.
- You would rather grow an agent from nothing than delete what you don't need from a worked example.
- You want the scaffolding (tests, evals, limits, tracing) around an agent you write yourself.

**Look elsewhere when**

- One of the patterns fits. Start from it. [`single`](../single/) is the same agent with a worked example and recipes for tools, dynamic instructions and multi-turn history, and [Which pattern should I use?](../../docs/pages/choosing-a-pattern.md) helps you choose.

**What it shows**

- A structured output type (`BlankOutput`) and an injectable dependencies dataclass (`BlankDeps`)
- Instructions loaded from a prompt file (`prompts/blank.txt`)
- `USAGE_LIMITS` on every run, and the `RaiseContentFilterError` capability
- A commented recipe for dynamic instructions, for when the prompt depends on runtime state

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

```bash
uv run python scripts/add_agent.py blank --name newsletter
```
