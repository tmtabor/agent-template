"""Recorded runs are kept as the model wrote them: ruff must not reformat the code inside them."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_recorded_runs_are_excluded_from_ruff():
    """ruff formats Python inside Markdown, so a re-recorded transcript whose code uses single quotes made
    `ruff format --check` fail in CI. The transcripts are a record, not source."""
    ruff = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["ruff"]
    assert "examples/*/sample_run.md" in ruff["extend-exclude"]
