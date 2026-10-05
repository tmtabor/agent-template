"""The offline suite never depends on the model or key that .env configures."""

import os

import pytest

from conftest import command_line, markexpr_from, selects_live_tests


@pytest.mark.parametrize(
    ("args", "expression"),
    [
        (["-q"], ""),
        (["-m", "eval", "examples"], "eval"),
        (["-m=eval or not eval"], "eval or not eval"),
        (["-meval", "-q"], "eval"),
        (["-q", "-m", "not eval"], "not eval"),
        (["--maxfail", "1"], ""),  # a long option that merely starts with -m is not -m
    ],
)
def test_the_marker_expression_is_read_from_the_command_line(args, expression):
    assert markexpr_from(args) == expression


@pytest.mark.parametrize(
    ("markexpr", "live"),
    [
        ("not eval", False),
        ("", False),
        ("eval", True),
        ("eval or not eval", True),
        ("not eval and not slow", False),
    ],
)
def test_only_a_marker_expression_that_selects_eval_is_live(markexpr: str, live: bool):
    assert selects_live_tests(markexpr) is live


def test_the_offline_suite_runs_on_the_builtin_test_model():
    if selects_live_tests(markexpr_from(command_line())):
        pytest.skip("this run selects the live tests, which use the configured model")
    from agent.config import settings

    assert os.environ["AGENT_MODEL"] == "test"
    assert settings.model == "test"
