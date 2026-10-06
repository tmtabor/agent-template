# Contributing

Issues and pull requests are welcome. This is a template that people copy and reshape, so the bar for a change is: does it make a project that starts from here better, and can we show that it works?

## What helps most

- **Bug reports.** Say what you ran, what you expected, what happened, and which model and versions (`uv run python --version`, `AGENT_MODEL`). A failing command beats a description.
- **Fixes** to an example, the scaffolding (`scripts/add_agent.py`), the docs or the tests.
- **A new pattern.** Open an issue first and describe the problem it solves that no current example does. A new example is a bigger commitment than it looks (see [Changing or adding an example](#changing-or-adding-an-example)).
- **Corrections to claims.** If a README or guide says something that is not true for you, that is a bug.

## Set up

```bash
git clone https://github.com/tmtabor/agent-template.git
cd agent-template
uv sync --group dev
cp .env.example .env        # add the key for the provider AGENT_MODEL names
```

```bash
uv run ruff check .             # lint
uv run ruff format .            # format
uv run pytest                   # the offline tests: no network, no API key, free
uv run pytest -m eval           # real model calls, costs money; see "Evals" in the README
```

The offline suite is what CI runs on every push and pull request, together with `ruff check` and `ruff format --check`. It does not need a key. It does skip the tests of the four examples that need extra packages or a running service (`code_mode`, `temporal`, `rag`, `mcp_tools`); those run in the release check below.

## Before you open a pull request

1. `uv run ruff check . && uv run ruff format --check . && uv run pytest` passes.
2. If you changed an example, run its checks against a real model. This needs a provider key, and Docker if the example has a service:

   ```bash
   uv run python scripts/release_check.py <example>
   ```

   It costs a few cents. It runs the example's offline tests, its live tests and a smoke run, and it fails unless every line of the example's `agent.py` was exercised. See [MAINTAINING.md](MAINTAINING.md#the-release-check) for what it checks and why it is not part of CI.
3. If your change is visible to someone who has already copied the template (a setting, a default, a convention, what the scaffold writes), add a line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md), in the same commit.
4. If you changed docs, remember the site is generated from the repo's own files; see [Documentation](#documentation).

## Changing or adding an example

The examples are the product, so they are held to a higher standard than the rest of the code: every one has been run against a real model, and the checks require it. The full rules are in [AGENTS.md](AGENTS.md#writing-a-new-example); in short, an example has:

- **Real tools and invented data.** No placeholder tool that echoes its input (a real model loops on it), and a domain a model cannot know, so a correct answer proves the pattern worked.
- **Offline tests that cover every branch**, using scripted models, asserting on side effects (a ledger, what was retrieved) and not on the model's wording.
- **Live tests** with an unambiguous right answer, assertions that hold for any capable model, and a check that every agent in the example really ran.
- **A README** with a "See it run" line, a recorded run (`--record`), and a place in `DISPLAY_ORDER` in `scripts/example_manifest.py`.

Then `uv run python scripts/release_check.py <example> --record`, and commit the transcript it writes. Say in the pull request which model recorded it.

## Conventions

- **Python 3.13, ruff** (line length 100). `asyncio_mode = "auto"` is set, so async tests need no decorator.
- **Tests assert behavior, not wording.** Nothing in the suite may call a real model unless it is marked `eval`.
- **No secrets, no personal data** in code, fixtures or transcripts.
- **Commit messages** say what changed and why; the history is the explanation of the design. Small, focused pull requests get reviewed faster.
- **The template stays small.** A change that adds a dependency to every user needs a strong reason; an example's extra packages are declared in its `example.toml` and installed only when someone adds that example.

## Documentation

The documentation site is generated from the README, `AGENTS.md`, `CHANGELOG.md`, the `examples/` folders and two hand-written guides in `docs/pages/`. To change the site, change those files. Preview it with:

```bash
uv run --group docs mkdocs serve           # http://127.0.0.1:8000
uv run --group docs mkdocs build --strict  # fails on any broken link
```

[MAINTAINING.md](MAINTAINING.md#the-documentation-site) has the details, including the README headings the site depends on.

## Security

Do not open a public issue for a security problem: report it privately, as [SECURITY.md](SECURITY.md) describes.

## License

By contributing you agree that your contribution is licensed under the project's [BSD 3-Clause license](LICENSE).
