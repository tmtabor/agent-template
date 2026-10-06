#!/usr/bin/env python3
"""Add an agent to this project by copying an example pattern from examples/.

Usage:
    uv run python scripts/add_agent.py                       # interactive menu
    uv run python scripts/add_agent.py supervisor --name triage
    uv run python scripts/add_agent.py blank --name newsletter
    uv run python scripts/add_agent.py --prune               # drop the examples you don't need

Run it once per agent you want; each can use a different pattern. It copies the
example's module to agent/agents/<name>.py and its prompts to agent/prompts/,
scaffolds a smoke test (tests/test_agents_<name>.py) and an eval starter
(evals/test_<name>.py), and installs the example's extra dependencies with
`uv add`. There is no shared "primary" agent: import yours directly, e.g.

    from agent.agents.triage import triage_agent
"""

from __future__ import annotations

import argparse
import json
import keyword
import re
import shutil
import subprocess
import sys
from pathlib import Path

from example_manifest import REPO_ROOT, Example, ManifestError, discover

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# `--prune` keeps the blank example (and the scripts) so agents can still be added.
PRUNE_KEEP = {"blank"}
PRUNE_PATHS = [
    # The docs site: generated from the repo's files, so it goes when the examples do.
    "docs",
    "site",
    "mkdocs.yml",
    ".github/workflows/docs.yml",
    "examples/README.md",  # the generated index of the examples
    "scripts/examples_index.py",
    "tests/test_docs.py",
    # Maintainer tooling for the example library: the live release gate and its tests.
    "scripts/release_check.py",
    "scripts/record_example.py",
    "scripts/live_run.py",
    "tests/test_examples.py",
    "tests/test_add_agent.py",
    "tests/test_live_tools.py",
    "tests/test_trace.py",
    # Documents about the template itself, not about the project it became.
    "MAINTAINING.md",
    "CONTRIBUTING.md",
    "SECURITY.md",  # how to report a problem in the template itself
    "badges",  # the coverage badge's data, written by the release check
]


def to_pascal_case(name: str) -> str:
    return "".join(word.capitalize() for word in name.split("_"))


# --- Targets and validation ---------------------------------------------------------


def targets(root: Path, name: str, example: Example) -> dict[str, Path]:
    """Every file a new agent adds, so collisions are caught before anything is written."""
    paths = {
        "module": root / "agent" / "agents" / f"{name}.py",
        "test": root / "tests" / f"test_agents_{name}.py",
        "eval": root / "evals" / f"test_{name}.py",
        "fixture": root / "evals" / "fixtures" / f"{name}.json",
    }
    for prompt in example.prompt_files:
        paths[f"prompt:{prompt.name}"] = (
            root / "agent" / "prompts" / prompt_target(prompt.name, example.name, name)
        )
    if example.service_dir.is_dir():
        # The example's service (server, Dockerfile, compose file) is a separate deployable, so it
        # goes beside the project's agents rather than inside agent/.
        paths["service"] = root / "services" / name
    return paths


def prompt_target(filename: str, example_name: str, name: str) -> str:
    """Prompt files are named after their example (`single.txt`, `single_critic.txt`)."""
    stem = filename.removesuffix(".txt")
    if stem == example_name or stem.startswith(f"{example_name}_"):
        return name + stem.removeprefix(example_name) + ".txt"
    return f"{name}_{stem}.txt"


def validate_name(root: Path, name: str, example: Example) -> str | None:
    """Return an error message if `name` can't be used, else None."""
    if not NAME_RE.match(name):
        return (
            f"'{name}' is not a valid snake_case identifier "
            "(start with a lowercase letter, then lowercase letters, digits or underscores)"
        )
    if keyword.iskeyword(name):
        return f"'{name}' is a Python keyword"
    for path in targets(root, name, example).values():
        if path.exists():
            return f"{path.relative_to(root)} already exists — pick another --name"
    return None


# --- Rendering ----------------------------------------------------------------------


def rename(text: str, example: Example, name: str) -> str:
    """Apply the example → agent renaming to source text."""
    if example.templated:
        # The example's own name is a placeholder token (`blank_agent`, `BlankOutput`).
        text = text.replace(example.name, name)
        return text.replace(to_pascal_case(example.name), to_pascal_case(name))
    # Otherwise only prompt references change; every other symbol keeps its example name,
    # which is safe because each agent lives in its own module.
    pattern = re.compile(rf'load_prompt\(\s*"{re.escape(example.name)}((?:_\w+)?)"')
    return pattern.sub(lambda m: f'load_prompt("{name}{m.group(1)}"', text)


def service_skip(example: Example, name: str) -> str:
    """Lines that skip a generated test unless the example's services are up (empty if it has none)."""
    if not example.service_specs:
        return ""
    envs = sorted(spec.env for spec in example.service_specs.values())
    return (
        "import os\n\nimport pytest\n\n"
        f"pytestmark = pytest.mark.skipif(\n"
        f"    not all(os.environ.get(name) for name in {envs!r}),\n"
        f'    reason="needs the service running: see services/{name}/",\n'
        ")\n\n"
    )


def smoke_test_source(example: Example, name: str) -> str:
    run = rename(example.run, example, name)
    # Agents the manifest configures for smoke tests, by their (renamed) variable names.
    configured = {rename(var, example, name): cfg for var, cfg in example.smoke.items()}
    tools = sorted({t for cfg in configured.values() for t in cfg.call_tools})

    imports = ""
    if tools:
        imports += "from pydantic_ai.messages import ToolReturnPart\n"
    if configured:
        imports += "from pydantic_ai.models.test import TestModel\n"
    if imports:
        imports += "\n"
    names = ", ".join(sorted([*configured, run]))

    # The autouse safety net in tests/conftest.py already gives every agent a TestModel that
    # calls no tools. Override only the agents the manifest configures: to opt in to tools, or
    # to supply an output their validators accept (TestModel's generated junk would fail them).
    overrides = []
    for variable, cfg in configured.items():
        kwargs = f"call_tools={list(cfg.call_tools)!r}"
        if cfg.output is not None:
            kwargs += f", custom_output_args={cfg.output!r}"
        overrides.append(f"{variable}.override(model=TestModel({kwargs}))")
    call = f'result = await {run}("Smoke test input")'
    if len(overrides) == 1:
        body = f"    with {overrides[0]}:\n        {call}\n"
    elif overrides:
        inner = "".join(f"        {o},\n" for o in overrides)
        body = f"    with (\n{inner}    ):\n        {call}\n"
    else:
        body = f"    {call}\n"

    check = "    assert result.output is not None\n    assert result.steps\n"
    if tools:
        check += (
            "    called = {\n"
            "        part.tool_name\n"
            "        for message in result.all_messages()\n"
            "        for part in message.parts\n"
            "        if isinstance(part, ToolReturnPart)\n"
            "    }\n"
            f"    assert {{{', '.join(map(repr, tools))}}} <= called\n"
        )
    return (
        f'"""Smoke test for the {name} agent '
        f"(scaffolded by scripts/add_agent.py from the {example.name} example).\n\n"
        "Runs the whole flow through the agent's run helper. The autouse fixture in\n"
        "tests/conftest.py overrides every Agent under agent.agents with a TestModel, so this\n"
        'runs with no API key and no cost.\n"""\n\n'
        f"{imports}"
        f"from agent.agents.{name} import {names}\n\n"
        f"{service_skip(example, name)}\n"
        f"async def test_{name}_runs_with_test_model():\n"
        f"{body}{check}"
    )


def eval_service_skip(example: Example, name: str) -> str:
    """Skip every eval in the module unless the example's services are up (empty if it has none)."""
    if not example.service_specs:
        return ""
    envs = sorted(spec.env for spec in example.service_specs.values())
    return (
        f"if not all(os.environ.get(name) for name in {envs!r}):\n"
        f'    pytest.skip("needs the service running: see services/{name}/", allow_module_level=True)\n'
    )


def eval_source(example: Example, name: str) -> str:
    run = rename(example.run, example, name)
    return (
        f'"""Evals for the {name} agent (scaffolded by scripts/add_agent.py).\n\n'
        "These make real model calls: run with `uv run pytest -m eval` (needs an API key,\n"
        f"costs money). Grow the dataset by adding cases to evals/fixtures/{name}.json — see\n"
        'evals/helpers.py for the optional keys that add behavioral checks.\n"""\n\n'
        f"{'import os' + chr(10) if example.service_specs else ''}"
        "import pytest\n\n"
        f"from agent.agents.{name} import {run}\n"
        "from evals.helpers import load_fixtures, output_text, run_fixture_dataset\n"
        "from evals.judge import judge_response\n\n"
        f"SMOKE_INPUT = {example.smoke_input!r}\n\n"
        f"{eval_service_skip(example, name)}\n"
        "@pytest.mark.eval\n"
        f"async def test_{name}_returns_output():\n"
        f"    result = await {run}(SMOKE_INPUT)\n"
        "    assert output_text(result.output)\n\n\n"
        "@pytest.mark.eval\n"
        f"async def test_{name}_fixture_dataset():\n"
        f'    await run_fixture_dataset("{name}", load_fixtures("{name}"), {run})\n\n\n'
        "@pytest.mark.eval\n"
        f"async def test_{name}_quality_judge():\n"
        '    """An LLM judge (AGENT_JUDGE_MODEL) scores the answer against your criteria."""\n'
        f"    result = await {run}(SMOKE_INPUT)\n"
        "    verdict = await judge_response(\n"
        "        task=SMOKE_INPUT,\n"
        "        response=output_text(result.output),\n"
        '        criteria="The response directly and accurately addresses the task.",\n'
        "        threshold=0.6,\n"
        "    )\n"
        "    assert verdict.passed, (\n"
        '        f"Judge score {verdict.score:.2f} below threshold. Reasoning: {verdict.reasoning}"\n'
        "    )\n"
    )


def fixture_source(example: Example) -> str:
    cases = [{"name": "smoke", "inputs": {"user_input": example.smoke_input}}]
    return json.dumps(cases, indent=2) + "\n"


# --- Actions ------------------------------------------------------------------------


def add(root: Path, example: Example, name: str, *, install: bool = True) -> list[Path]:
    """Copy `example` into the project at `root` as agent `name`. Returns the files written."""
    error = validate_name(root, name, example)
    if error:
        raise ValueError(error)

    paths = targets(root, name, example)
    contents = {
        "module": rename(example.source.read_text(encoding="utf-8"), example, name),
        "test": smoke_test_source(example, name),
        "eval": eval_source(example, name),
        "fixture": fixture_source(example),
    }
    for prompt in example.prompt_files:
        text = prompt.read_text(encoding="utf-8")
        contents[f"prompt:{prompt.name}"] = (
            rename(text, example, name) if example.templated else text
        )

    for key, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if key == "service":
            shutil.copytree(example.service_dir, path, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            path.write_text(contents[key], encoding="utf-8")

    written = list(paths.values())
    format_python([p for p in written if p.suffix == ".py"], root)
    if install and example.dependencies:
        subprocess.run(["uv", "add", *example.dependencies], cwd=root, check=False)
    return written


def format_python(files: list[Path], root: Path) -> None:
    """Sort imports and reformat generated files so they pass the repo's lint and style.

    Hand-formatting a template for every possible identifier length isn't reliable.
    """
    ruff = shutil.which("ruff")
    command = [ruff] if ruff else [sys.executable, "-m", "ruff"]
    paths = [str(f) for f in files]
    try:
        subprocess.run(
            [*command, "check", "--select", "I", "--fix", "--quiet", *paths],
            cwd=root,
            check=False,
            capture_output=True,
        )
        subprocess.run([*command, "format", *paths], cwd=root, check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"warning: could not auto-format generated files with ruff ({exc})", file=sys.stderr)
        print("  run `uv run ruff check --fix . && uv run ruff format .` manually", file=sys.stderr)


def prune_targets(root: Path) -> list[Path]:
    found = [
        d
        for d in sorted((root / "examples").glob("*/"))
        if d.is_dir() and (d / "example.toml").exists() and d.name not in PRUNE_KEEP
    ]
    found += [root / p for p in PRUNE_PATHS if (root / p).exists()]
    return found


def remove_dependency_group(pyproject: str, group: str) -> str:
    """`pyproject` without its `[dependency-groups]` entry named `group` (a no-op if absent)."""
    return re.sub(rf"^{re.escape(group)} = \[\n(?:.*\n)*?\]\n", "", pyproject, flags=re.MULTILINE)


def prune(root: Path, *, relock: bool = False) -> None:
    """Delete the example library's scaffolding, keeping `blank` so agents can still be added.

    Also drops the `docs` dependency group from pyproject.toml (nothing left uses it) and, with
    `relock`, refreshes uv.lock to match.
    """
    for path in prune_targets(root):
        shutil.rmtree(path) if path.is_dir() else path.unlink()

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8")
        edited = remove_dependency_group(text, "docs")
        if edited != text:
            pyproject.write_text(edited, encoding="utf-8")
            if relock:
                subprocess.run(["uv", "lock", "--quiet"], cwd=root, check=False)


# --- CLI ----------------------------------------------------------------------------


def choose_example(examples: list[Example]) -> Example:
    print("Which pattern?\n")
    for i, e in enumerate(examples, 1):
        print(f"  {i:>2}. {e.name:<16} {e.summary}")
    while True:
        answer = input("\nNumber or name: ").strip()
        for i, e in enumerate(examples, 1):
            if answer in (str(i), e.name):
                return e
        print(f"  '{answer}' isn't on the list.")


def setup_notes(example: Example, name: str, *, install_needed: bool) -> list[str]:
    """What to tell the user to do after the agent is copied, one line each (blank lines included)."""
    lines: list[str] = []
    if example.dependencies and install_needed:
        lines.append(f"Install its dependencies: uv add {' '.join(example.dependencies)}")
    if example.env:
        # Some of these are optional (they have a default); the example's README says which.
        lines.append(
            f"Environment variables it reads, to set in .env if you need to: {', '.join(example.env)}"
        )
    if example.services:
        compose = f"services/{name}/docker-compose.yml"
        lines.append(
            f"Its service ({', '.join(example.services)}) is in services/{name}/. Start it, then tell the agent where it is:"
        )
        lines.append(f"    docker compose -f {compose} up -d --wait")
        for spec in example.service_specs.values():
            lines.append(
                f"    docker compose -f {compose} port {spec.name} {spec.port}   # host:port Docker chose"
            )
            lines.append(
                f"    set {spec.env} to {spec.url.replace('{address}', '<that host:port>')}"
            )
        lines.append("")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("example", nargs="?", help="example to copy (omit for a menu)")
    parser.add_argument("--name", help="snake_case name for the new agent (default: the example)")
    parser.add_argument(
        "--no-install", action="store_true", help="skip `uv add` for the example's dependencies"
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="delete the examples (except blank), docs and their tests",
    )
    parser.add_argument("--yes", action="store_true", help="don't ask before pruning")
    args = parser.parse_args(argv)
    interactive = sys.stdin.isatty()

    if args.prune:
        if args.example or args.name:
            parser.error("--prune takes no example or --name")
        doomed = prune_targets(REPO_ROOT)
        if not doomed:
            print("Nothing to prune.")
            return 0
        print("This will delete:")
        for path in doomed:
            print(f"  {path.relative_to(REPO_ROOT)}")
        if not args.yes:
            if not interactive:
                print("error: refusing to prune non-interactively without --yes", file=sys.stderr)
                return 1
            if input("Delete these? [y/N] ").strip().lower() != "y":
                print("Aborted.")
                return 1
        prune(REPO_ROOT, relock=True)
        print("Pruned. `blank` is kept so you can still add agents.")
        return 0

    try:
        examples = discover(REPO_ROOT / "examples")
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not examples:
        print("error: no examples found under examples/", file=sys.stderr)
        return 1

    by_name = {e.name: e for e in examples}
    if args.example:
        if args.example not in by_name:
            print(f"error: unknown example '{args.example}'", file=sys.stderr)
            print(f"available: {', '.join(by_name)}", file=sys.stderr)
            return 1
        example = by_name[args.example]
    elif interactive:
        example = choose_example(examples)
    else:
        print("error: name an example, e.g. `add_agent.py supervisor`", file=sys.stderr)
        print(f"available: {', '.join(by_name)}", file=sys.stderr)
        return 1

    name = args.name
    if not name:
        name = input(f"Name for the agent [{example.name}]: ").strip() if interactive else ""
        name = name or example.name

    error = validate_name(REPO_ROOT, name, example)
    if error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    written = add(REPO_ROOT, example, name, install=not args.no_install)
    for path in written:
        print(f"Created {path.relative_to(REPO_ROOT)}")

    run = rename(example.run, example, name)
    print(f"\nDone — the {name} agent is in agent/agents/{name}.py. Import it directly:")
    print(f"    from agent.agents.{name} import {run}")
    print(f"    result = await {run}(...)   # result.output is the answer\n")
    for line in setup_notes(example, name, install_needed=args.no_install):
        print(line)
    print(
        "Next steps:\n"
        f"  1. Edit agent/agents/{name}.py and its prompt(s) in agent/prompts/\n"
        "  2. uv run pytest             (smoke test, no API key needed)\n"
        "  3. uv run pytest -m eval     (real model calls)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
