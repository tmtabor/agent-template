# FAQ

## Getting started

### Should I use the template or clone it?

Either. **Use this template** on GitHub creates a new repository with a fresh history, which is what you want for your own project. Cloning is for trying it out or contributing. Both give you the same files. See [Get started](../../README.md#get-started).

### Do I need an API key to begin?

No. `uv run pytest` runs the offline tests with a stand-in model: no network, no key, no cost. You need a key to run an agent for real, and then only for the provider your `AGENT_MODEL` names.

### Why does my program fail at import with a key error?

By design. `Settings` asks Pydantic AI to build the provider behind `AGENT_MODEL` when it is imported, so a missing or misspelled key fails immediately and clearly, not at the first request. Put the key in `.env` (see `.env.example`) or the environment.

### Which models can I use?

Any model Pydantic AI supports: change `AGENT_MODEL` to a model string such as `openai:gpt-5.2` or `google:gemini-3.1-flash-lite`. The default is `anthropic:claude-sonnet-5-5`. The committed recorded runs were made with `google:gemini-3.1-flash-lite`. See [Configuration](../../README.md#configuration).

### Can I use a local model?

Yes, with `ollama:<model>` and `OLLAMA_BASE_URL`. The model has to call tools and return valid structured output, and small local models often cannot, which shows up as validation errors. That is a limit of the model, not of the template.

## Using the patterns

### Do I have to install everything the examples need?

No. `add_agent.py` installs only what the example you picked declares (for instance `temporalio` for `temporal`). Nothing else is added to your project.

### Which examples need Docker?

Three run a service: [`rag`](../../examples/rag/) (Chroma), [`temporal`](../../examples/temporal/) and [`mcp_tools`](../../examples/mcp_tools/). `add_agent.py` copies the service into `services/<name>/` and prints how to start it. The others need nothing running.

### Can I use more than one pattern in a project?

Yes. Run `add_agent.py` once per agent; each gets its own module and can use a different pattern. There is no shared "primary" agent. To combine patterns inside one flow, see [Which pattern should I use?](choosing-a-pattern.md).

### Why does `python examples/temporal/agent.py` fail?

Temporal's sandbox imports a workflow's module by name, so a workflow cannot live in `__main__`. Start it as a module: `python -m examples.temporal.agent`.

### Why does `rag` ask me to set an embedding model?

It follows your LLM's provider: Google and OpenAI work out of the box. Anthropic has no embedding model, so with an Anthropic LLM set `AGENT_EMBEDDING_MODEL` in `.env` (for example `google:gemini-embedding-001`).

### I only want some of the examples. Can I delete the rest?

`uv run python scripts/add_agent.py --prune` deletes the examples you did not use (keeping `blank`), the docs site, the release check and their tests. Nothing under `agent/` or `evals/` depends on `examples/`.

### How do I get later changes to the template?

Your project is a copy, with no link back, so there is nothing to merge automatically. Each release's [changelog](../../CHANGELOG.md) lists what changed and has an "Upgrade notes" entry when you need to act. Compare the changed files by hand.

## Testing and cost

### Do the tests cost money?

`uv run pytest` is free. `uv run pytest -m eval` calls a real model and costs money (cents for the examples). The release check, which maintainers run, costs about a cent or two for all seventeen examples on a small model.

### Why are some tests skipped?

The default environment has only the template's dependencies, so the tests of examples that need an extra package or a running service skip (`code_mode`, `temporal`, `rag`, `mcp_tools`). The release check runs them in their own environments. See [Maintaining](../../MAINTAINING.md#the-release-check).

### Why did my tests call a real model?

The root `conftest.py` forces the offline test model unless `eval` appears in the `-m` expression. So a selection such as `-m "eval or not eval"` counts as asking for real calls. Run offline and live tests as separate commands.

### What stops a runaway agent from spending my money?

Each agent has `USAGE_LIMITS` (a cap on model requests and tokens), and `AGENT_COST_LIMIT` adds a spend cap in USD for models with known prices. Exceeding a limit raises `UsageLimitExceeded` instead of running on. See [Usage limits](../../README.md#usage-limits).

## Observability

### Do I need Logfire?

No. Runs are traced with OpenTelemetry through Logfire's instrumentation. With no `LOGFIRE_TOKEN` the traces print to the console; set one to send them to Logfire. See [Observability](../../README.md#observability).

## Is it ready for production?

It is a starting point, not a finished product. The patterns have been run against a real model, their tests cover every line of the example code, and each has a recorded run you can read. What you must still do is replace the invented data and the placeholder tools with your own, write evals for your task, set limits suited to it, and decide how your services run for real (a Temporal worker as its own process, Chroma beyond a single container, and so on). The [next steps](../../README.md#next-steps) in the README walk through it.

## Something is wrong

Open an [issue](https://github.com/tmtabor/agent-template/issues). A failing command, the model you used and the output are the most useful things to include. To change something, see [Contributing](../../CONTRIBUTING.md).
