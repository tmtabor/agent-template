# Security Policy

## Reporting a vulnerability

Please report security issues privately through GitHub's
[**Report a vulnerability**](https://github.com/tmtabor/agent-template/security/advisories/new)
button (repository **Security** tab → **Advisories**). Do not open a public issue for security
problems.

You should get an acknowledgement within a few days. If a fix is warranted, it will be developed
under a private advisory and disclosed once a patch is available.

## Supported versions

Only the latest release and `main`. This is a template: your project is a copy with no link back to
it, so a fix reaches you only when you apply it. Fixes are described in [CHANGELOG.md](CHANGELOG.md),
with an "Upgrade notes" entry when you need to act.

## Scope

In scope: the code in this repository.

- The template itself: configuration and settings handling (`agent/config.py`), logging and tracing
  (`agent/logging.py`), and anything that could leak a key or prompt content you did not mean to share.
- The scaffolding and release tooling in `scripts/`.
- The examples, including their services (`examples/*/service/`), which are published on `127.0.0.1`
  only, and the `code_mode` example's limits on what model-written code can do.
- The CI and documentation workflows in `.github/`.

Out of scope:

- Vulnerabilities in the libraries and services the template builds on (Pydantic AI, Logfire, Monty,
  Chroma, Temporal, MCP and their SDKs, model providers): report those to their maintainers.
- What a model says or does when it is prompted adversarially. The examples show guardrails and
  approval gates, but they are starting points, not a hardened product: deploying an agent safely is
  your responsibility (see the FAQ's "Is it ready for production?").
- The invented data in the examples.

## For projects built from this template

Keep your provider keys out of the repository (`.env` is git-ignored here), set
`AGENT_LOG_CONTENT=false` if traces may carry sensitive prompts, and give a project of your own its
own `SECURITY.md`; this one describes how to report a problem in the template.
