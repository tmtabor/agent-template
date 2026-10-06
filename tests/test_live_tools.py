"""The live-verification tooling, tested offline.

record_example.py and release_check.py make real model calls, but everything around that one
call works from a RunResult or from subprocess results, so it is tested here with TestModel and
fake runners. No network, no API key.
"""

import dataclasses
import json
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

import live_run
import release_check
from example_manifest import DEFAULT_COST_BUDGET_USD, ManifestError, load
from live_run import render_transcript, run_live, step_cost, tools_called, verify
from record_example import RESULT_PREFIX, Outcome, record_one
from tests.examples_support import EXAMPLES, import_example, smoke_overrides


def example(name: str):
    return next(e for e in EXAMPLES if e.name == name)


async def live(name: str, *, model: str = "test"):
    """A LiveRun of a real example, driven offline by its manifest's TestModels."""
    ex = example(name)
    module = import_example(ex)
    with smoke_overrides(ex, module):
        return await run_live(ex, getattr(module, ex.run), model)


# --- LiveRun, usage and verification -----------------------------------------------------


async def test_a_live_run_reports_tokens_and_has_no_cost_for_an_unpriced_model():
    run = await live("router")
    assert run.tokens > 0
    assert step_cost(run.result.steps[0]) is None  # TestModel has no price
    assert run.cost is None


async def test_cost_is_summed_across_steps_when_every_step_is_priced(monkeypatch):
    run = await live("router")
    monkeypatch.setattr(live_run, "step_cost", lambda step: Decimal("0.01"))
    assert run.cost == Decimal("0.02")  # two steps


async def test_cost_is_unknown_if_any_step_is_unpriced(monkeypatch):
    run = await live("router")
    prices = iter([Decimal("0.01"), None])
    monkeypatch.setattr(live_run, "step_cost", lambda step: next(prices))
    assert run.cost is None


async def test_a_good_run_passes_verification():
    assert verify(await live("supervisor")) == []


async def test_tools_called_lists_real_tools_not_the_output_tool():
    run = await live("supervisor")
    assert tools_called(run.result) == {"delegate_to_analyst", "delegate_to_writer"}


async def test_verification_fails_when_an_expected_tool_was_never_called():
    run = await live("router")
    run = dataclasses.replace(run, example=dataclasses.replace(run.example, expected_tools=("x",)))
    failures = verify(run)
    assert len(failures) == 1 and "expected tool" in failures[0]


async def test_verification_fails_over_budget(monkeypatch):
    run = await live("router")
    monkeypatch.setattr(live_run, "step_cost", lambda step: Decimal("1"))
    failures = verify(run)
    assert any("exceeds" in f for f in failures)


async def test_verification_fails_on_a_wrongly_labeled_step():
    run = await live("router")
    run = dataclasses.replace(run, example=dataclasses.replace(run.example, name="other"))
    assert any("not labeled" in f for f in verify(run))


# --- Transcript -----------------------------------------------------------------------------


async def test_the_transcript_shows_input_steps_tools_and_result():
    text = render_transcript(await live("supervisor"))

    assert text.startswith("# Sample run: Supervisor / workers")
    assert "Recorded " in text and "`test`" in text
    assert "## Input" in text and "pros and cons of remote work" in text
    assert "### 1. `supervisor`" in text
    assert "called `delegate_to_analyst(" in text
    assert "`delegate_to_writer` returned:" in text
    assert "## Result" in text and "```json" in text
    assert "scripts/record_example.py supervisor" in text


async def test_a_flow_transcript_has_a_section_per_step():
    text = render_transcript(await live("pipeline"))
    for index, role in enumerate(("outline", "draft", "polish"), 1):
        assert f"### {index}. `pipeline.{role}`" in text


def test_code_the_model_wrote_is_shown_as_code_not_a_clipped_argument():
    from pydantic_ai.messages import ToolCallPart

    code = "total = 0\nfor i in range(3):\n    total += i\n\ntotal"
    text = live_run.describe_call(ToolCallPart("run_code", {"code": code}))

    assert text.startswith("ran this code in the sandbox:")
    assert (
        "    ```python\n    total = 0\n    for i in range(3):" in text
    )  # indented under its bullet
    assert text.rstrip().endswith("```") and "run_code(" not in text


def test_very_long_code_is_clipped():
    from pydantic_ai.messages import ToolCallPart

    text = live_run.describe_call(ToolCallPart("run_code", {"code": "x = 1\n" * 1000}))
    assert text.count("x = 1") < 1000  # clipped to MAX_CODE_CHARS before being indented
    assert text.count("x = 1") <= live_run.MAX_CODE_CHARS // len("x = 1\n") + 1
    assert " …" in text  # and says so


def test_an_ordinary_tool_call_is_still_one_clipped_line():
    from pydantic_ai.messages import ToolCallPart

    text = live_run.describe_call(ToolCallPart("get_expense", {"expense_id": "X101"}))
    assert text == 'called `get_expense({"expense_id": "X101"})`'
    # A tool that merely takes a "code" argument is not the sandbox.
    other = live_run.describe_call(ToolCallPart("apply_coupon", {"code": "SAVE10"}))
    assert other.startswith("called `apply_coupon(")


def test_a_run_that_paused_for_approval_is_described_readably_not_as_a_raw_repr():
    from pydantic_ai import DeferredToolRequests
    from pydantic_ai.messages import ToolCallPart

    call = ToolCallPart(
        "issue_refund",
        {"order_id": "A100", "amount_usd": 84.5},
        tool_call_id="c1",
        provider_details={"thought_signature": "x" * 500},  # opaque provider noise
    )
    text = live_run.fenced(DeferredToolRequests(approvals=[call]))

    assert "The run paused: waiting for a decision on" in text
    assert 'approve  issue_refund({"order_id": "A100", "amount_usd": 84.5})' in text
    assert "thought_signature" not in text and "x" * 50 not in text


def test_a_call_waiting_on_an_external_result_is_described_too():
    from pydantic_ai import DeferredToolRequests
    from pydantic_ai.messages import ToolCallPart

    text = live_run.fenced(DeferredToolRequests(calls=[ToolCallPart("run_report", {"id": 7})]))
    assert 'external run_report({"id": 7})' in text


def test_other_long_unstructured_output_is_clipped():
    text = live_run.fenced("y" * 5000)
    assert len(text) < 2100 and text.startswith("```text")


async def test_long_values_are_clipped():
    assert len(live_run.clip("x" * 5000)) < live_run.MAX_FIELD_CHARS + 5
    assert live_run.clip("short") == "short"


# --- record_one -------------------------------------------------------------------------------


async def test_a_passing_example_writes_its_transcript(tmp_path: Path):
    ex = dataclasses.replace(example("router"), path=tmp_path)
    module = import_example(ex)
    with smoke_overrides(ex, module):
        outcome = await record_one(ex, module.run_router, "test")

    assert outcome.status == "passed" and outcome.steps == 2 and outcome.failures == []
    assert (tmp_path / "sample_run.md").read_text().startswith("# Sample run: Router")


async def test_no_write_leaves_the_transcript_alone(tmp_path: Path):
    ex = dataclasses.replace(example("router"), path=tmp_path)
    module = import_example(ex)
    with smoke_overrides(ex, module):
        outcome = await record_one(ex, module.run_router, "test", write=False)
    assert outcome.status == "passed" and not (tmp_path / "sample_run.md").exists()


async def test_a_failed_check_never_overwrites_the_last_good_transcript(tmp_path: Path):
    (tmp_path / "sample_run.md").write_text("last good transcript")
    ex = dataclasses.replace(example("router"), path=tmp_path, expected_tools=("nope",))
    module = import_example(ex)
    with smoke_overrides(ex, module):
        outcome = await record_one(ex, module.run_router, "test")

    assert outcome.status == "failed" and outcome.failures
    assert (tmp_path / "sample_run.md").read_text() == "last good transcript"


async def test_an_exception_is_reported_as_a_failure_not_raised(tmp_path: Path):
    async def broken(user_input: str):
        raise RuntimeError("provider is down")

    ex = dataclasses.replace(example("router"), path=tmp_path)
    outcome = await record_one(ex, broken, "test")
    assert outcome.status == "failed" and "RuntimeError: provider is down" in outcome.error


# --- release_check ----------------------------------------------------------------------------


def with_deps(name: str = "router", **changes):
    return dataclasses.replace(example(name), dependencies=("httpx>=0.28", "rich"), **changes)


def test_an_isolated_run_layers_only_the_examples_declared_dependencies():
    command = release_check.live_command(with_deps(), record=True)
    assert command[:6] == ["uv", "run", "--with", "httpx>=0.28", "--with", "rich"]
    assert command[6:] == ["python", "scripts/record_example.py", "router", "--json"]


def test_an_example_without_dependencies_adds_no_with_flags():
    assert "--with" not in release_check.live_command(example("router"), record=True)


def test_checking_does_not_write_transcripts_unless_recording():
    assert "--no-write" in release_check.live_command(example("router"), record=False)
    assert "--no-write" not in release_check.live_command(example("router"), record=True)


def test_the_offline_command_targets_the_example_in_its_isolated_environment():
    command = release_check.offline_command(with_deps())
    assert "--with" in command and "-a" in command and "eval" not in command  # no real model calls
    assert "examples/router" in command


def test_an_isolated_example_also_runs_the_generic_tests_that_would_skip_it_elsewhere():
    command = release_check.offline_command(with_deps())
    for path in release_check.GENERIC_TESTS:
        assert path in command
    # Narrowed to this example, and without the transcript check (a new example has none yet).
    assert command[-2:] == ["-k", f"router and not {release_check.TRANSCRIPT_TEST}"]


def test_the_budget_becomes_a_hard_spend_cap():
    env = release_check.live_env(example("router"), {"AGENT_MODEL": "anthropic:x"})
    assert env["AGENT_COST_LIMIT"] == str(DEFAULT_COST_BUDGET_USD)


def test_the_startup_banner_is_silenced_in_the_subprocess():
    assert release_check.live_env(example("router"), {})["PYDANTIC_AI_NO_BANNER"] == "1"


def test_no_cap_is_set_for_a_local_model_or_over_a_cap_the_caller_chose():
    local = release_check.live_env(example("router"), {"AGENT_MODEL": "ollama:llama3"})
    assert "AGENT_COST_LIMIT" not in local
    chosen = release_check.live_env(example("router"), {"AGENT_COST_LIMIT": "0.05"})
    assert chosen["AGENT_COST_LIMIT"] == "0.05"


def completed(stdout: str = "", returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_the_outcome_is_read_from_the_result_line():
    sent = Outcome("router", "passed", steps=2, tokens=10, cost=0.01)
    stdout = f"✓ router  2 steps\n{sent.to_json()}\n"
    assert release_check.parse_outcome(example("router"), completed(stdout)) == sent


def test_a_process_with_no_result_line_is_a_failure_that_says_why():
    outcome = release_check.parse_outcome(
        example("router"), completed("", returncode=1, stderr="Traceback\nValueError: no key")
    )
    assert outcome.status == "failed" and "ValueError: no key" in outcome.error
    assert RESULT_PREFIX not in outcome.error


def test_the_summary_totals_spend_and_gates_on_failures():
    outcomes = [
        Outcome("a", "passed", tokens=100, cost=0.01),
        Outcome("b", "passed", tokens=50, cost=0.02),
    ]
    summary = release_check.summarize(outcomes)
    assert summary.ok and "2 passed, 0 failed" in summary.text and "150 tokens" in summary.text
    assert "$0.0300 spent" in summary.text

    bad = release_check.summarize([*outcomes, Outcome("c", "failed", error="boom")])
    assert not bad.ok and "1 failed" in bad.text


def test_unverified_examples_fail_the_check_unless_allowed():
    outcomes = [
        Outcome("a", "passed", cost=0.0),
        Outcome("t", "unverified", error="needs temporal"),
    ]
    assert not release_check.summarize(outcomes).ok
    assert release_check.summarize(outcomes, allow_unverified=True).ok


def test_unpriced_runs_are_called_out_rather_than_counted_as_free():
    summary = release_check.summarize([Outcome("a", "passed", tokens=5, cost=None)])
    assert "no price for: a" in summary.text


def stage_of(command) -> str:
    """Which stage of the check a command is, from its shape."""
    if "scripts/record_example.py" in command:
        return "smoke"
    if "report" in command:
        return "coverage"
    return "live_tests" if "eval" in command else "offline"


class FakeRunner:
    """Records each command and returns scripted results, in place of real subprocesses."""

    def __init__(self, fail: str | None = None):
        self.calls: list[tuple[list[str], dict]] = []
        self.fail = fail

    @property
    def stages(self) -> list[str]:
        return [stage_of(c) for c, _ in self.calls]

    def __call__(self, command, env):
        self.calls.append((list(command), env))
        stage = stage_of(command)
        if stage == "smoke":
            name = command[command.index("scripts/record_example.py") + 1]
            return completed(Outcome(name, "passed", steps=1, cost=0.001).to_json())
        if stage == self.fail:
            return completed("", 1, f"{stage} failed: 1 failed")
        return completed("ok")


def check(examples, runner, **kwargs):
    return release_check.check_examples(
        examples, record=False, model="m", runner=runner, env={}, log=lambda _: None, **kwargs
    )


def test_each_example_runs_its_live_tests_then_its_smoke_run_with_its_budget():
    runner = FakeRunner()
    ours = [example("router"), dataclasses.replace(example("pipeline"), cost_budget_usd=0.5)]
    outcomes = check(ours, runner)

    assert [o.status for o in outcomes] == ["passed", "passed"]
    assert runner.stages == ["live_tests", "smoke", "live_tests", "smoke"]
    # Every paid stage carries the example's own budget as a hard spend cap.
    assert [c[1]["AGENT_COST_LIMIT"] for c in runner.calls] == [
        str(DEFAULT_COST_BUDGET_USD),
        str(DEFAULT_COST_BUDGET_USD),
        "0.5",
        "0.5",
    ]


def test_an_example_with_dependencies_runs_its_offline_tests_first():
    runner = FakeRunner()
    check([with_deps()], runner)
    assert runner.stages == ["offline", "live_tests", "smoke"]


def test_a_failing_isolated_offline_run_skips_everything_that_costs_money():
    runner = FakeRunner(fail="offline")
    (outcome,) = check([with_deps()], runner)
    assert outcome.status == "failed" and "offline tests failed in isolation" in outcome.error
    assert runner.stages == ["offline"]


def test_failing_live_tests_skip_the_smoke_run_and_the_transcript():
    runner = FakeRunner(fail="live_tests")
    (outcome,) = check([example("router")], runner)
    assert outcome.status == "failed" and "live tests failed" in outcome.error
    assert "live_tests failed: 1 failed" in outcome.error
    assert runner.stages == ["live_tests"]  # no smoke run, so nothing was recorded


def test_live_tests_run_in_the_isolated_environment_and_append_to_the_coverage_data():
    command = release_check.live_tests_command(with_deps())
    assert command[:6] == ["uv", "run", "--with", "httpx>=0.28", "--with", "rich"]
    assert command[6:12] == ["coverage", "run", "-a", "-m", "pytest", "-m"]
    assert "eval" in command and command[-1] == "examples/router"


def test_the_offline_suite_runs_under_coverage_without_appending():
    command = release_check.offline_suite_command()
    assert command[:5] == ["uv", "run", "coverage", "run", "-m"] and "-a" not in command


def test_the_first_stage_skips_the_transcript_check_and_the_last_runs_it():
    """A new example has no transcript until the gate records it, so checking first would block it."""
    first = release_check.offline_suite_command()
    assert first[-2:] == [
        "-k",
        f"not {release_check.TRANSCRIPT_TEST} and not {release_check.BADGE_TEST}",
    ]

    last = release_check.transcript_command([example("router"), example("pipeline")])
    assert last[-2:] == ["-k", f"{release_check.TRANSCRIPT_TEST} and (router or pipeline)"]
    assert "coverage" not in last  # a plain, quick check


def test_the_transcript_gate_reports_whether_every_example_has_one():
    ok = release_check.transcript_gate(
        [example("router")], runner=lambda c, e: completed("1 passed")
    )
    assert ok.ok and ok.report == "all present and current" and "sample_run.md" in ok.title
    bad = release_check.transcript_gate(
        [example("router")], runner=lambda c, e: completed("record it: ...", returncode=1)
    )
    assert not bad.ok and "record it" in bad.report


def test_a_missing_transcript_fails_the_check_even_if_every_example_passed():
    outcomes = [Outcome("a", "passed", cost=0.0)]
    missing = release_check.Coverage(False, "no transcript", title="Recorded runs:")
    summary = release_check.summarize(outcomes, transcripts=missing)
    assert not summary.ok and "Recorded runs:" in summary.text and "no transcript" in summary.text


def test_an_examples_service_code_is_covered_too():
    command = release_check.coverage_command([example("mcp_tools"), example("router")])
    assert command[-1] == (
        "--include=examples/mcp_tools/agent.py,examples/mcp_tools/service/server.py,"
        "examples/router/agent.py"
    )


def test_the_coverage_report_covers_only_the_examples_that_were_checked():
    command = release_check.coverage_command([example("router"), example("pipeline")])
    assert command[-1] == "--include=examples/router/agent.py,examples/pipeline/agent.py"


def test_the_coverage_gate_passes_or_fails_on_the_reports_exit_code():
    ok = release_check.coverage_gate(
        [example("router")], runner=lambda c, e: completed("TOTAL 100%")
    )
    assert ok.ok and "100%" in ok.report
    bad = release_check.coverage_gate(
        [example("router")], runner=lambda c, e: completed("fan_out  98%  122", returncode=2)
    )
    assert not bad.ok and "122" in bad.report


def test_uncovered_example_code_fails_the_check_even_if_every_example_passed():
    outcomes = [Outcome("a", "passed", cost=0.0)]
    gap = release_check.Coverage(False, "fan_out/agent.py  98%  missing: 122")
    summary = release_check.summarize(outcomes, coverage=gap)
    assert not summary.ok and "missing: 122" in summary.text
    assert release_check.summarize(outcomes, coverage=release_check.Coverage(True, "100%")).ok
    assert release_check.summarize(outcomes).ok  # not measured (--skip-tests): no gate


# --- Manifest keys ---------------------------------------------------------------------------


def test_the_live_check_keys_default_sensibly():
    assert example("router").cost_budget_usd == DEFAULT_COST_BUDGET_USD
    assert example("router").expected_tools == ()
    assert example("supervisor").expected_tools == ("delegate_to_analyst", "delegate_to_writer")
    assert example("tool_calling").expected_tools == ("python_release_notes",)


@pytest.mark.parametrize("budget", ["0", "-1", '"cheap"', "true"])
def test_a_bad_budget_is_rejected(tmp_path: Path, budget: str):
    (tmp_path / "agent.py").write_text("")
    (tmp_path / "example.toml").write_text(
        'title="x"\npattern="x"\nsummary="x"\nsmoke_input="x"\n'
        f"cost_budget_usd = {budget}\n[entrypoint]\ndeps='D'\nrun='r'\n"
    )
    with pytest.raises(ManifestError, match="cost_budget_usd"):
        load(tmp_path)


# --- What a failed stage says ---

PYTEST_FAILURE = """\
........F.
=================================== FAILURES ===================================
_____________ test_the_plan_groups_independent_lookups _____________
>       assert len(output.waves[0]) >= 2
E       assert 1 >= 2
E        +  where 1 = len([['s1']][0])
------------------------------ Captured log call -------------------------------
INFO     httpx2:_client.py:1923 HTTP Request: POST https://example.test "HTTP/1.1 200 OK"
INFO     httpx2:_client.py:1923 HTTP Request: POST https://example.test "HTTP/1.1 200 OK"
=========================== short test summary info ============================
FAILED examples/x/test_live.py::test_the_plan_groups_independent_lookups - assert 1 >= 2
1 failed, 9 passed in 18.7s
"""


def test_a_failed_stage_reports_the_failure_not_the_log_lines_after_it():
    summary = release_check.failure_summary(PYTEST_FAILURE)
    assert "FAILED examples/x/test_live.py::test_the_plan_groups_independent_lookups" in summary
    assert "E       assert 1 >= 2" in summary
    assert "HTTP Request" not in summary


def test_a_failed_stage_with_no_pytest_failure_falls_back_to_the_last_lines():
    output = "\n".join(f"line {i}" for i in range(20))
    assert (
        release_check.failure_summary(output) == "line 15 | line 16 | line 17 | line 18 | line 19"
    )


def test_a_long_failure_is_cut_to_a_readable_length():
    output = "\n".join(f"FAILED test_{i}" for i in range(50))
    assert release_check.failure_summary(output).count("FAILED") == release_check.MAX_FAILURE_LINES


# --- The coverage badge ---------------------------------------------------------------------------

COVERAGE_REPORT = """\
Name                                    Stmts   Miss  Cover   Missing
---------------------------------------------------------------------
examples/blank/agent.py                    32      0   100%
examples/rag/agent.py                     128      0   100%
---------------------------------------------------------------------
TOTAL                                     160      0   100%
"""


def passed(name: str = "a") -> Outcome:
    return Outcome(name, "passed")


def earned(**overrides) -> bool:
    arguments = dict(
        all_examples=True,
        measuring=True,
        outcomes=[passed("a"), passed("b")],
        coverage=release_check.Coverage(True, COVERAGE_REPORT),
    )
    return release_check.badge_is_earned(**{**arguments, **overrides})


def test_the_coverage_percentage_is_read_from_the_reports_total_line():
    assert release_check.coverage_percent(COVERAGE_REPORT) == 100.0
    assert release_check.coverage_percent("TOTAL      10      1    90%\n") == 90.0
    assert release_check.coverage_percent("TOTAL      10      1  89.5%\n") == 89.5
    assert release_check.coverage_percent("no total here") is None


def test_the_badge_json_is_what_shields_io_reads():
    assert release_check.coverage_badge(100.0) == {
        "schemaVersion": 1,
        "label": "coverage",
        "message": "100%",
        "color": "brightgreen",
    }
    assert release_check.coverage_badge(92.5)["color"] == "yellow"
    assert release_check.coverage_badge(92.5)["message"] == "92.5%"


def test_a_complete_clean_run_earns_the_badge():
    assert earned()


@pytest.mark.parametrize(
    "overrides",
    [
        {"all_examples": False},  # only some examples were checked
        {"measuring": False},  # the offline suite did not run, so there is no coverage to report
        {"outcomes": [passed("a"), Outcome("b", "failed")]},
        {"outcomes": [passed("a"), Outcome("b", "unverified")]},  # e.g. Docker was missing
        {"outcomes": []},
        {"coverage": None},
        {"coverage": release_check.Coverage(False, COVERAGE_REPORT)},  # the gate itself failed
        {"coverage": release_check.Coverage(True, "no total line")},
    ],
    ids=[
        "subset",
        "no-suite",
        "failed",
        "unverified",
        "nothing-ran",
        "no-coverage",
        "gate-failed",
        "unreadable",
    ],
)
def test_anything_less_than_a_complete_clean_run_does_not_earn_the_badge(overrides):
    assert not earned(**overrides)


def test_writing_the_badge_records_the_percentage_and_creates_the_folder(tmp_path):
    path = tmp_path / "badges" / "coverage.json"
    percent = release_check.write_coverage_badge(
        release_check.Coverage(True, COVERAGE_REPORT), path
    )
    assert percent == 100.0
    written = json.loads(path.read_text())
    assert written["message"] == "100%" and written["schemaVersion"] == 1
    assert path.read_text().endswith("\n")


def test_the_committed_badge_file_is_valid_if_present():
    path = release_check.BADGE_PATH
    if path.exists():
        badge = json.loads(path.read_text())
        assert badge["schemaVersion"] == 1 and badge["label"] == "coverage"
        assert re.fullmatch(r"\d+(\.\d+)?%", badge["message"])


def test_the_gates_first_stage_leaves_out_the_check_of_the_file_the_gate_writes():
    """Otherwise an old badge file (say, from before a format change) would stop the gate that fixes it."""
    command = release_check.offline_suite_command()
    assert release_check.BADGE_TEST in command[-1]
    # and the name really selects that test, so the exclusion is not a dead string
    assert any(
        release_check.BADGE_TEST in name
        for name in dir(sys.modules[__name__])
        if name.startswith("test_")
    )
