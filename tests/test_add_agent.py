"""scripts/add_agent.py: copy each example into a scratch project and use it.

Each test works on a throwaway copy of the repo, so it exercises the real script
end to end: the copied module imports, its generated smoke test passes under
TestModel, its eval starter collects, and prompt paths are rewritten correctly.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import add_agent
from example_manifest import REPO_ROOT, discover
from tests.examples_support import example_ids

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
    if ex.dependencies:
        pytest.skip("needs its own environment")
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
