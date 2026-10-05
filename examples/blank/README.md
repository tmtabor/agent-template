# Blank

An empty agent: one output type, one prompt file, no tools. Every symbol is renamed to the
name you choose, so `--name newsletter` gives you `newsletter_agent`, `NewsletterOutput`,
`NewsletterDeps` and `run_newsletter_agent`.

```bash
uv run python scripts/add_agent.py blank --name newsletter
```
