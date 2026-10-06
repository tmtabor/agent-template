# Maintaining

For the people who release this template and run its tooling. If you only want to use or contribute to it, you do not need this: see the [README](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## The release check

`TestModel` cannot tell you an example works: it ignores what tools return and what instructions say, so a placeholder tool or a half-written prompt passes every offline test. (The `tool_calling` example once shipped a tool that echoed its query, and a real model looped on it until the request limit.) So before a release, run the check yourself, locally:

```bash
# The provider key for AGENT_MODEL must be in .env or the environment.
# Docker must be running if any example declares a service.
uv run python scripts/release_check.py                 # every example
uv run python scripts/release_check.py router rag      # or just some
uv run python scripts/release_check.py --record        # also rewrite each sample_run.md
uv run python scripts/release_check.py --allow-unverified   # don't fail when Docker is missing
```

It makes real model calls and costs money: a few minutes and about a cent or two for the whole set on a small model. It:

1. runs the offline suite under coverage;
2. runs each example in its own `uv run` environment, with only its declared `dependencies` layered on and a hard spend cap from its `cost_budget_usd`: first its **live tests** (real-model assertions on behavior, a requirement that every agent the example defines actually ran, and a run of its `__main__` demo), then a **smoke run** (`scripts/record_example.py`: the run returns a `RunResult`, steps are labeled for the example, the manifest's `expected_tools` were really called, the cost stayed in budget);
3. fails unless **every line of every `examples/*/agent.py` and service `server.py` was executed** by the offline and live tests together (`fail_under = 100` in `pyproject.toml`);
4. checks that every example's recorded run exists and is current, and prints pass, fail and unverified counts with tokens and spend;
5. if the **whole library** passed (every example, tests included, nothing unverified), writes `badges/coverage.json`, the data for the README's coverage badge.

Things to know:

- **It is manual on purpose.** It spends money and needs your key, so it is not in CI. CI (`.github/workflows/ci.yml`) runs only lint, the format check and the offline suite.
- **Services.** An example that declares `services` is started with `docker compose up --build --wait` for the duration of its checks and always torn down, images included. If Docker is not usable it is reported *unverified* with the reason (and fails the check unless `--allow-unverified`), never as passed.
- **Any capable model.** The check uses whatever `AGENT_MODEL` names, and the live tests assert behavior that holds for any capable model, not one model's wording. A model that cannot call tools and return valid structured output (small local ones often cannot) fails, which is a verdict on the model. A provider outage (a `503`, say) also fails an example; run it again.
- **The coverage badge.** The badge in the README reads `badges/coverage.json` through shields.io. The release check writes it only after a complete clean run: a subset of the examples, `--skip-tests`, an example that failed or went unverified, or a failed coverage gate each leave the last good badge alone. It records only the percentage (the badge reads `coverage: 100%`), so it is only as fresh as the last release check you committed. Commit it with the release. (The number is the release check's: CI alone exercises less, because it skips the examples that need extra packages or a service.)
- **Transcripts.** `--record` rewrites each example's `sample_run.md` from a real run; a failed run never overwrites the last good one. The model that recorded each transcript is in its header, and the committed ones were recorded with `google:gemini-3.1-flash-lite`. Commit what it writes.
- **A failure** is reported with pytest's `FAILED` line and the assertion. To see one example in full: `uv run pytest -m eval examples/<name>`.
- **Why the default test run skips some tests.** `uv run pytest` runs in an environment with only the template's dependencies, so the tests of examples that need extra packages or a service skip (`code_mode`, `temporal`, `rag`, `mcp_tools`). The release check is what runs them, in their own environments, and is the only thing that proves them.

## Cutting a release

1. Run the release check (above) with `--record` and commit the transcripts and `badges/coverage.json`.
2. Bump `version` in `pyproject.toml` and run `uv lock`.
3. In `CHANGELOG.md`, rename `[Unreleased]` to the new version with its date, add a fresh empty `[Unreleased]` above it, and update the compare links at the bottom. Every user-visible change should already have its line there; see [Changelog](AGENTS.md#changelog) in the design notes for what counts.
4. Commit, tag `vX.Y.Z`, and push the commit and the tag.

## The documentation site

The site is built by MkDocs Material and published to GitHub Pages by `.github/workflows/docs.yml` on every push to `main` that touches the docs sources. It is served at **https://tmtabor.io/agent-template/** (`tmtabor.github.io/agent-template` redirects there), and `site_url` in `mkdocs.yml` must stay in step.

Almost nothing in it is written twice. `docs/gen_pages.py` generates the pages from the repo's own files:

| Page | Source |
|---|---|
| Home, Getting started, Configuration, Guides | the README, split by its `##` headings |
| Patterns (one per example) | each example's README, `sample_run.md` and source |
| Contributing, Maintaining | `CONTRIBUTING.md`, `MAINTAINING.md` |
| Design notes | `AGENTS.md` |
| Changelog | `CHANGELOG.md` |
| Which pattern should I use?, FAQ | the two hand-written pages in `docs/pages/` |

So to change the docs, change those files. Consequences worth knowing:

- **README headings are an interface.** Renaming a `##` section the site uses fails the build loudly (`SectionNotFound`) until `README_PAGES` in `docs/gen_pages.py` is updated.
- **The home page's use-case tabs** are the README's `###` sections under "What are you building?": each becomes a tab, and on GitHub they are ordinary sections.
- **A new example** gets its page and navigation entry automatically. It needs a `sample_run.md`, and optionally a slot in `DISPLAY_ORDER` in `scripts/example_manifest.py`.
- **`examples/README.md` is generated** (`uv run python scripts/examples_index.py`); `tests/test_docs.py` fails if it is stale.
- **Write for GitHub, expect MkDocs.** The generator adds the blank line MkDocs needs before a list that follows a bold line, but anything else that GitHub forgives and MkDocs does not needs a look at the rendered page; `--strict` only catches broken links.
- **The preview does not watch the READMEs.** `mkdocs serve` reloads when something under `docs/` or `mkdocs.yml` changes, but the pages are generated from files outside `docs/` (the README, the examples' READMEs, `AGENTS.md`). After editing one, restart `mkdocs serve`, or you will be looking at the old page.
- **`docs/plans/` is not published.**

```bash
uv run --group docs mkdocs serve           # preview at http://127.0.0.1:8000
uv run --group docs mkdocs build --strict  # what the workflow runs
```

One-time setup for a fork or a new copy: in the repository's **Settings → Pages**, set **Source** to **GitHub Actions**. `mkdocs` is pinned `<2`: MkDocs 2.0 will break plugins and themes.

## Versions and pins

- **Services are pinned to an exact image version**, never `latest`, so the release check runs against the same server every time. A client library and its server move together: `chromadb-client` 1.5 with `chromadb/chroma:1.5.9`, `temporalio` with `temporalio/temporal:1.8.0`.
- **`pydantic-ai-harness` is pre-1.0 and its minor version tracks Pydantic AI's** (0.54 goes with 2.54), so bump them together.
- After bumping any of these, run the release check for the affected examples.

## Pruning

`uv run python scripts/add_agent.py --prune` deletes the examples a user did not choose, plus this tooling: the docs, the release check and their tests, the badge data, and this file, `CONTRIBUTING.md` and `SECURITY.md`.
