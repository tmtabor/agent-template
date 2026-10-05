"""Repo-wide pytest setup. Runs before anything under agent/ is imported.

Offline tests must not depend on whichever model and key `.env` happens to configure, so unless
the command line selects the live (`eval`) tests, the model is forced to Pydantic AI's built-in
`test` model. That makes the offline suite — including the first stage of
scripts/release_check.py — hermetic: it passes with no provider key, whatever `AGENT_MODEL`
says. Live runs (`pytest -m eval ...`) keep your configured model, because reaching it is the
point.

This has to happen when this file is imported, not in a `pytest_configure` hook: pytest imports
tests/conftest.py (and with it agent.config, which reads the model once) before any hook runs,
so the only thing available this early is the command line.
"""

import os
import shlex
import sys


def markexpr_from(args: list[str]) -> str:
    """The `-m` marker expression in `args`, or "" when there isn't one.

    Handles `-m EXPR`, `-mEXPR` and `-m=EXPR`. The default (`-m 'not eval'` from addopts in
    pyproject.toml) is offline, so no `-m` on the command line means offline.
    """
    expression = ""
    for i, arg in enumerate(args):
        if arg == "-m" and i + 1 < len(args):
            expression = args[i + 1]
        elif arg.startswith("-m=") or (arg.startswith("-m") and not arg.startswith("--")):
            expression = arg[3:] if arg.startswith("-m=") else arg[2:]
    return expression


def selects_live_tests(markexpr: str) -> bool:
    """True when the expression selects the `eval` tests (`eval`, `eval or not eval`, …)."""
    return "eval" in markexpr.replace("not eval", "")


def command_line() -> list[str]:
    return [*shlex.split(os.environ.get("PYTEST_ADDOPTS", "")), *sys.argv[1:]]


if not selects_live_tests(markexpr_from(command_line())):
    os.environ["AGENT_MODEL"] = "test"
