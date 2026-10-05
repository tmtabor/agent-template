"""Every example is well-formed and runs under TestModel.

Parametrized over the manifests discovered in examples/, so adding an example adds
its checks. Each one is imported in place; an example whose declared dependencies
aren't installed in this environment is skipped, not failed.
"""

from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ToolReturnPart

from example_manifest import EXAMPLES_DIR, ManifestError, load
from tests.examples_support import EXAMPLES, example_ids, import_example, smoke_model


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
def test_entrypoint_names_resolve(example):
    module = import_example(example)
    for attr in (example.agent, example.deps, example.run):
        assert hasattr(module, attr), f"{example.module} has no {attr}"


@pytest.mark.parametrize("example", example_ids())
async def test_example_runs_with_test_model(example):
    module = import_example(example)
    main_agent = getattr(module, example.agent)
    deps = getattr(module, example.deps)()

    # The safety net calls no tools; opt in to the ones the manifest names.
    with main_agent.override(model=smoke_model(example)):
        result = await main_agent.run(example.smoke_input, deps=deps)
    assert result.output is not None

    # Opted-in tools must really have been called, or the opt-in is silently dead.
    called = {
        part.tool_name
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }
    assert set(example.smoke_tools) <= called


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


def agents_in(module) -> list[Agent]:
    return [v for v in vars(module).values() if isinstance(v, Agent)]


@pytest.mark.parametrize("example", example_ids())
def test_agents_are_labeled_with_the_example_name(example):
    """Labels follow the module name, so a copy is labeled with its chosen name."""
    agents = agents_in(import_example(example))
    assert agents, f"{example.module} defines no Agent"
    for found in agents:
        assert found.name == example.name or (found.name or "").startswith(f"{example.name}.")
