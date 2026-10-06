"""scripts/add_agent.py: copy each example into a scratch project and use it.

Each test works on a throwaway copy of the repo, so it exercises the real script
end to end: the copied module imports, its generated smoke test passes under
TestModel, its eval starter collects, and prompt paths are rewritten correctly.
"""

import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import add_agent
from example_manifest import REPO_ROOT, discover
from tests.examples_support import example_ids, import_example

COPIED = ("agent", "examples", "evals", "scripts")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    for name in COPIED:
        shutil.copytree(REPO_ROOT / name, tmp_path / name, ignore=ignore)
    (tmp_path / "tests").mkdir()
    for name in ("__init__.py", "conftest.py", "agent_finder.py", "examples_support.py"):
        shutil.copy(REPO_ROOT / "tests" / name, tmp_path / "tests" / name)
    shutil.copy(REPO_ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    # A fresh clone has no agents; guard against this repo gaining one by accident.
    assert [p.name for p in (tmp_path / "agent" / "agents").glob("*.py")] == ["__init__.py"]
    return tmp_path


def pytest_in(project: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=project,
        capture_output=True,
        text=True,
    )


def agent_names(project: Path, name: str) -> list[str]:
    """Names of every Agent in the copied agent.agents.<name>, read in the scratch project."""
    snippet = (
        "import json, importlib\n"
        "from pydantic_ai import Agent\n"
        f"m = importlib.import_module('agent.agents.{name}')\n"
        "print(json.dumps([v.name for v in vars(m).values() if isinstance(v, Agent)]))\n"
    )
    env = {**os.environ, "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "dummy")}
    out = subprocess.run(
        [sys.executable, "-c", snippet], cwd=project, capture_output=True, text=True, env=env
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.splitlines()[-1])


def example(name: str):
    return next(e for e in discover() if e.name == name)


def test_the_repo_ships_no_agents():
    agents = [p.name for p in (REPO_ROOT / "agent" / "agents").glob("*.py")]
    assert agents == ["__init__.py"]


@pytest.mark.parametrize("ex", example_ids())
def test_added_agent_runs_and_its_evals_collect(project: Path, ex):
    # Skips if the example's dependencies, or a service its generated smoke test would call, are missing.
    import_example(ex, running=True)
    add_agent.add(project, ex, "my_agent", install=False)

    module = project / "agent" / "agents" / "my_agent.py"
    assert module.is_file()
    assert (project / "tests" / "test_agents_my_agent.py").is_file()
    assert (project / "evals" / "fixtures" / "my_agent.json").is_file()
    # Adding an agent never rewires anything shared.
    init = Path("agent") / "agents" / "__init__.py"
    assert (project / init).read_text() == (REPO_ROOT / init).read_text()

    result = pytest_in(project, "tests/test_agents_my_agent.py")
    assert result.returncode == 0, result.stdout + result.stderr

    # Trace labels follow the name the user chose, not the example's.
    labels = agent_names(project, "my_agent")
    assert labels
    assert all(n == "my_agent" or n.startswith("my_agent.") for n in labels), labels

    # Generated files must pass the repo's own lint and format checks (a user's CI runs them).
    generated = [
        str(p)
        for p in (
            module,
            project / "tests" / "test_agents_my_agent.py",
            project / "evals" / "test_my_agent.py",
        )
    ]
    for check in (["check"], ["format", "--check"]):
        lint = subprocess.run(
            [sys.executable, "-m", "ruff", *check, *generated],
            cwd=project,
            capture_output=True,
            text=True,
        )
        assert lint.returncode == 0, lint.stdout + lint.stderr

    collected = pytest_in(project, "--collect-only", "-m", "eval", "evals/test_my_agent.py")
    assert collected.returncode == 0, collected.stdout + collected.stderr
    assert "test_my_agent_returns_output" in collected.stdout


def test_prompts_are_renamed_to_the_new_agent(project: Path):
    add_agent.add(project, example("single"), "triage", install=False)
    source = (project / "agent" / "agents" / "triage.py").read_text()
    assert 'load_prompt("triage")' in source
    assert (project / "agent" / "prompts" / "triage.txt").is_file()


def test_blank_symbols_are_renamed(project: Path):
    add_agent.add(project, example("blank"), "newsletter", install=False)
    source = (project / "agent" / "agents" / "newsletter.py").read_text()
    for symbol in (
        "newsletter_agent",
        "NewsletterOutput",
        "NewsletterDeps",
        "run_newsletter_agent",
    ):
        assert symbol in source
    assert "blank" not in source.lower()
    assert 'load_prompt("newsletter")' in source
    assert "newsletter agent" in (project / "agent" / "prompts" / "newsletter.txt").read_text()


def test_an_examples_dependencies_are_installed_with_uv_add_and_only_when_asked(
    project: Path, monkeypatch
):
    """code_mode is the first shipped example with a runtime dependency, so this is the real case."""
    calls: list[tuple[list[str], Path]] = []
    real_run = subprocess.run

    def record(command, *args, **kwargs):
        if command[:2] == ["uv", "add"]:
            calls.append((list(command), kwargs.get("cwd")))
            return subprocess.CompletedProcess(command, 0)
        return real_run(command, *args, **kwargs)  # ruff formatting still runs for real

    monkeypatch.setattr(add_agent.subprocess, "run", record)
    ex = example("code_mode")
    assert ex.dependencies == ("pydantic-ai-harness[code-mode]>=0.54,<1",)

    add_agent.add(project, ex, "calendar", install=False)
    assert calls == []  # --no-install: nothing is installed

    add_agent.add(project, ex, "calendar_two", install=True)
    assert calls == [(["uv", "add", *ex.dependencies], project)]

    add_agent.add(project, example("single"), "plain", install=True)
    assert len(calls) == 1  # an example with no dependencies runs no `uv add` at all


def test_an_example_with_a_service_brings_its_service_along(project: Path):
    ex = example("mcp_tools")
    written = add_agent.add(project, ex, "calendar", install=False)

    service = project / "services" / "calendar"
    assert service in written
    assert {p.name for p in service.iterdir()} == {"Dockerfile", "docker-compose.yml", "server.py"}
    assert not list(service.rglob("__pycache__"))  # no build debris
    assert (service / "server.py").read_text() == (ex.service_dir / "server.py").read_text()


def test_an_example_without_a_service_gets_no_services_folder(project: Path):
    add_agent.add(project, example("router"), "support", install=False)
    assert not (project / "services").exists()


def test_an_existing_service_folder_is_never_overwritten(project: Path):
    (project / "services" / "calendar").mkdir(parents=True)
    with pytest.raises(ValueError, match="services/calendar already exists"):
        add_agent.add(project, example("mcp_tools"), "calendar", install=False)


def test_the_generated_tests_skip_unless_the_service_is_running(project: Path):
    """A copied agent's smoke test and evals need its service; without it they skip, not fail."""
    add_agent.add(project, example("mcp_tools"), "calendar", install=False)
    smoke = (project / "tests" / "test_agents_calendar.py").read_text()
    evals = (project / "evals" / "test_calendar.py").read_text()
    assert "pytest.mark.skipif" in smoke and "MCP_SERVER_URL" in smoke
    assert "allow_module_level=True" in evals and "MCP_SERVER_URL" in evals

    env = {**os.environ, "MCP_SERVER_URL": ""}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/test_agents_calendar.py",
        ],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0 and "1 skipped" in result.stdout, result.stdout + result.stderr
    collected = pytest_in(project, "--collect-only", "-m", "eval", "evals/test_calendar.py")
    assert collected.returncode in (0, 5), (
        collected.stdout + collected.stderr
    )  # skipped module: no error


def test_only_runtime_dependencies_are_installed_not_test_dependencies(project: Path, monkeypatch):
    calls = []
    real_run = subprocess.run
    monkeypatch.setattr(
        add_agent.subprocess,
        "run",
        lambda command, *a, **k: (
            calls.append(list(command)) or subprocess.CompletedProcess(command, 0)
            if command[:2] == ["uv", "add"]
            else real_run(command, *a, **k)
        ),
    )
    ex = dataclasses.replace(example("mcp_tools"), dependencies=("httpx>=0.28",))
    add_agent.add(project, ex, "calendar", install=True)
    assert calls == [
        ["uv", "add", "httpx>=0.28"]
    ]  # the server half is for testing, not for using the agent


def test_the_same_example_can_be_added_twice(project: Path):
    add_agent.add(project, example("supervisor"), "triage", install=False)
    add_agent.add(project, example("supervisor"), "escalation", install=False)
    result = pytest_in(project, "tests/test_agents_triage.py", "tests/test_agents_escalation.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_an_existing_agent_is_never_overwritten(project: Path):
    add_agent.add(project, example("single"), "triage", install=False)
    with pytest.raises(ValueError, match="already exists"):
        add_agent.add(project, example("single"), "triage", install=False)


@pytest.mark.parametrize("name", ["Triage", "1triage", "my-agent", "class"])
def test_invalid_names_are_rejected(project: Path, name: str):
    assert add_agent.validate_name(project, name, example("single"))


def test_prune_keeps_blank_and_the_scripts(project: Path):
    (project / "mkdocs.yml").write_text("site_name: x\n")
    (project / "tests" / "test_docs.py").write_text("")
    (project / "scripts" / "release_check.py").write_text("")
    add_agent.prune(project)
    assert not (project / "scripts" / "release_check.py").exists()
    assert (project / "scripts" / "add_agent.py").exists()
    assert sorted(p.name for p in (project / "examples").iterdir() if p.is_dir()) == ["blank"]
    assert not (project / "mkdocs.yml").exists()
    assert not (project / "tests" / "test_docs.py").exists()
    assert not (project / "examples" / "README.md").exists()  # the generated index would be stale
    assert not (project / "scripts" / "examples_index.py").exists()
    # The docs dependency group goes with the docs; the dev group stays.
    pyproject = (project / "pyproject.toml").read_text()
    assert "mkdocs" not in pyproject and "dev = [" in pyproject
    # Agents can still be added after pruning.
    add_agent.add(project, example("blank"), "newsletter", install=False)
    assert (project / "agent" / "agents" / "newsletter.py").is_file()


def test_removing_a_dependency_group_leaves_the_others_untouched():
    text = (REPO_ROOT / "pyproject.toml").read_text()
    assert "docs = [" in text  # the repo has one to remove
    edited = add_agent.remove_dependency_group(text, "docs")
    assert "docs = [" not in edited and "mkdocs" not in edited
    assert "dev = [" in edited and "pytest>=" in edited and "[tool.pytest.ini_options]" in edited
    assert add_agent.remove_dependency_group(edited, "docs") == edited  # idempotent


# --- What the script tells you to do next ---


def test_the_setup_notes_say_which_variables_are_read_and_that_setting_them_is_optional():
    notes = add_agent.setup_notes(example("rag"), "support_docs", install_needed=False)
    text = "\n".join(notes)
    assert (
        "AGENT_EMBEDDING_MODEL" in text and "if you need to" in text
    )  # it has a default: not a demand
    assert "set CHROMA_URL to http://<that host:port>" in text
    assert "docker compose -f services/support_docs/docker-compose.yml up -d --wait" in text
    assert "Install its dependencies" not in text  # it was installed already


def test_the_setup_notes_give_the_install_command_when_nothing_was_installed():
    notes = add_agent.setup_notes(example("rag"), "support_docs", install_needed=True)
    assert notes[0] == "Install its dependencies: uv add chromadb-client>=1.5,<1.6"


def test_an_example_that_needs_nothing_has_no_setup_notes():
    assert add_agent.setup_notes(example("router"), "support", install_needed=False) == []
