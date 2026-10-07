"""The CI workflow keeps the checks that only make sense in the template's own repository."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_the_template_ships_no_agents_is_checked_in_ci_and_only_in_the_template_repository():
    """The guard moved out of the test suite (where a user's own agents broke it) into CI."""
    steps = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["test"]["steps"]
    guard = next(s for s in steps if s.get("name") == "The template ships no agents")
    assert guard["if"] == "github.repository == 'tmtabor/agent-template'"
    assert "agent/agents/*.py" in guard["run"]
