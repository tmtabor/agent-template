# Blank

An empty agent: one output type, one prompt file, no tools. Every symbol is renamed to the
name you choose, so `--name newsletter` gives you `newsletter_agent`, `NewsletterOutput`,
`NewsletterDeps` and `run_newsletter_agent`.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

```bash
uv run python scripts/add_agent.py blank --name newsletter
```
