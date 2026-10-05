"""Every example is well-formed and runs its whole flow under TestModel.

Parametrized over the manifests discovered in examples/, so adding an example adds its
checks. Each one is imported in place; an example whose declared dependencies aren't
installed in this environment is skipped, not failed.
"""

from pathlib import Path

import pytest
from pydantic_ai.messages import ToolReturnPart

from agent.runs import RunResult
from example_manifest import EXAMPLES_DIR, ManifestError, load
from tests.agent_finder import module_agents
from tests.examples_support import (
    EXAMPLES,
    example_ids,
    import_example,
    is_labeled,
    smoke_overrides,
)


def test_examples_exist():
    assert {e.name for e in EXAMPLES} >= {"blank", "single", "supervisor", "tool_calling"}


def test_every_example_directory_has_a_manifest():
    for path in EXAMPLES_DIR.iterdir():
        if path.is_dir() and not path.name.startswith(("_", ".")):
            assert (path / "example.toml").is_file(), f"{path} has no example.toml"


@pytest.mark.parametrize("example", example_ids())
def test_manifest_is_valid(example):
    loaded = load(example.path)
    assert loaded == example
    assert (example.path / "README.md").is_file()
    assert (example.path / "__init__.py").is_file()


@pytest.mark.parametrize("example", example_ids())
def test_prompt_files_are_named_after_the_example(example):
    for prompt in example.prompt_files:
        assert prompt.stem == example.name or prompt.stem.startswith(f"{example.name}_")


@pytest.mark.parametrize("example", example_ids())
def test_entrypoint_and_smoke_names_resolve(example):
    module = import_example(example)
    for attr in (example.deps, example.run):
        assert hasattr(module, attr), f"{example.module} has no {attr}"
    agent_ids = {id(a) for a in module_agents(module)}
    agent_variables = {name for name, value in vars(module).items() if id(value) in agent_ids}
    for variable in example.smoke:
        assert variable in agent_variables, (
            f"[smoke.{variable}] is not an Agent in {example.module}"
        )


@pytest.mark.parametrize("example", example_ids())
async def test_example_runs_its_whole_flow_with_test_model(example):
    """Drive `run` end to end: every agent in the flow runs, and the RunResult says how."""
    module = import_example(example)
    run = getattr(module, example.run)

    with smoke_overrides(example, module):
        result = await run(example.smoke_input)

    assert isinstance(result, RunResult)
    assert result.output is not None
    assert result.steps, "a run records at least one step"
    for step in result.steps:
        assert is_labeled(step.agent, example.name), (
            f"{step.agent!r} is not labeled for the example"
        )
        assert step.result.output is not None

    # One shared budget: the total covers every step and stays inside the example's limits.
    assert len(result.steps) <= result.usage.requests <= module.USAGE_LIMITS.request_limit

    # Opted-in tools must really have been called, or the opt-in is silently dead.
    called = {
        part.tool_name
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }
    for config in example.smoke.values():
        assert set(config.call_tools) <= called


@pytest.mark.parametrize("example", example_ids())
def test_agents_are_labeled_with_the_example_name(example):
    """Labels follow the module name, so a copy is labeled with its chosen name."""
    agents = module_agents(import_example(example))
    assert agents, f"{example.module} defines no Agent"
    for found in agents:
        assert is_labeled(found.name, example.name), found.name


@pytest.mark.parametrize("example", example_ids())
def test_every_example_has_a_recorded_sample_run_that_matches_it(example):
    """The transcript comes from scripts/release_check.py --record; this catches a stale one."""
    transcript = example.path / "sample_run.md"
    assert transcript.is_file(), f"record it: scripts/release_check.py --record {example.name}"
    text = transcript.read_text(encoding="utf-8")
    assert text.startswith(f"# Sample run: {example.title}")
    assert example.smoke_input in text, "the smoke input changed since this was recorded"
    assert "sample_run.md" in (example.path / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("toml", "message"),
    [
        ('title = "x"\n', "missing key"),
        ("bogus = 1\n", "missing key"),
    ],
)
def test_invalid_manifests_are_rejected(tmp_path: Path, toml: str, message: str):
    (tmp_path / "agent.py").write_text("")
    (tmp_path / "example.toml").write_text(toml)
    with pytest.raises(ManifestError, match=message):
        load(tmp_path)


VALID = """
title = "x"
pattern = "x"
summary = "x"
smoke_input = "x"
[entrypoint]
deps = "D"
run = "r"
"""


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("[smoke.some_agent]\nbogus = 1\n", "unknown key"),
        ("[smoke.some_agent]\ncall_tools = 3\n", "list of non-empty strings"),
        ("[smoke.some_agent]\noutput = 3\n", "must be a table"),
        ("[smoke]\nsome_agent = 3\n", "must be a table named for an agent"),
        ("[entrypoint]\nagent = 'a'\n", "exactly"),
    ],
)
def test_invalid_smoke_tables_are_rejected(tmp_path: Path, extra: str, message: str):
    (tmp_path / "agent.py").write_text("")
    body = VALID if "[entrypoint]" not in extra else VALID.split("[entrypoint]")[0]
    (tmp_path / "example.toml").write_text(body + extra)
    with pytest.raises(ManifestError, match=message):
        load(tmp_path)
