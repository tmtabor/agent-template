"""Every environment variable an example declares is documented where users look for it.

Examples read their own variables (the address of the service they need, an embedding model). A user
finds them in `.env.example` and in the README's Configuration section, so a new example that
declares one without documenting it fails here.
"""

import re
from pathlib import Path

from example_manifest import discover

ROOT = Path(__file__).resolve().parent.parent


def declared() -> dict[str, str]:
    """{variable: the example that declares it}: its `env` list and each service's address variable."""
    found: dict[str, str] = {}
    for example in discover():
        for name in example.env:
            found[name] = example.name
        for spec in example.service_specs.values():
            found[spec.env] = example.name
    return found


def configuration_section() -> str:
    text = (ROOT / "README.md").read_text()
    return re.search(r"^## Configuration\n(.*?)^## ", text, re.DOTALL | re.MULTILINE).group(1)


def test_some_examples_declare_variables():
    assert {"AGENT_EMBEDDING_MODEL", "CHROMA_URL", "MCP_SERVER_URL", "TEMPORAL_ADDRESS"} <= set(
        declared()
    )


def test_every_declared_variable_is_in_env_example_and_the_readme_configuration_section():
    env_example = (ROOT / ".env.example").read_text()
    readme = configuration_section()
    for name, example in declared().items():
        assert name in env_example, f"{name} (declared by {example}) is not in .env.example"
        assert name in readme, (
            f"{name} (declared by {example}) is not in the README's Configuration section"
        )
