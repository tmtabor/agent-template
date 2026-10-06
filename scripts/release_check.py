#!/usr/bin/env python3
"""The pre-release gate: offline tests, then every example run for real, in isolation.

Usage:
    uv run python scripts/release_check.py                 # check every example
    uv run python scripts/release_check.py router fan_out   # just these
    uv run python scripts/release_check.py --record         # also refresh each sample_run.md

What it does, in order:
  1. The offline test suite (`pytest`, no API key needed), under coverage. Stops here if it fails.
  2. For each example, in its own `uv run` process with only that example's declared
     `dependencies` layered on (so a missing declaration fails, and two examples never share
     an environment): its offline tests if it has extra dependencies; its live tests
     (`examples/<name>/test_live.py`, marked `eval`: real model calls that check behavior and
     that every agent in the example really ran); then a live run via scripts/record_example.py
     that checks the smoke input and records the transcript. Each run is capped by AGENT_COST_LIMIT
     from the example's `cost_budget_usd`.
  3. A coverage gate: every line of every example's `agent.py` must have been executed by the
     offline and live tests together, so no example code goes untested.
  4. A transcript check: every checked example has a sample_run.md that matches it. This runs
     *after* the live stage (and after --record writes them), not with the offline suite, because
     the transcripts are products of this very gate.
  5. A summary with total tokens and spend. Exits non-zero unless everything passed.
  6. If the *whole* library passed (every example, tests included, nothing unverified), it writes
     badges/coverage.json, which the README's coverage badge reads. A subset never writes it.

Makes real model calls: needs the provider key for AGENT_MODEL, and costs money (typically well
under a dollar for the whole library on the default model). An example that needs `services`
is reported as unverified, not passed, and fails the check unless --allow-unverified is given.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from example_manifest import REPO_ROOT, Example, ManifestError, discover
from record_example import RESULT_PREFIX, Outcome, describe, unverified
from services import ServiceStartError, ServicesUnavailable, run_process, running

Runner = Callable[[Sequence[str], dict[str, str]], "subprocess.CompletedProcess[str]"]


# Coverage is always run as `python -m coverage`, never as the `coverage` console script. Under
# `uv run --with <pkg>`, the script's launcher decides whether the extra packages are visible: the
# absolute-path launcher an older uv wrote into a long-lived .venv sees them, the relocatable `#!/bin/sh`
# launcher a fresh environment gets does not, so every example with extra dependencies silently skipped
# its tests (and the gate rightly failed it) on a fresh clone. `python -m` does not depend on the launcher.


def uv_run(example: Example | None, *args: str, tests: bool = False) -> list[str]:
    """`uv run` with the example's declared dependencies layered on, for an isolated run.

    `tests=True` adds its `test_dependencies` too: packages only its tests need (for instance the
    server half of a library, to run a service locally), which are not part of using the agent.
    """
    command = ["uv", "run"]
    if example is not None:
        for requirement in (*example.dependencies, *(example.test_dependencies if tests else ())):
            command += ["--with", requirement]
    return [*command, *args]


def needs_isolation(example: Example) -> bool:
    """Whether the generic tests would skip this example in the default environment, so it must
    also be tested in its own: it has dependencies, or tests that need extra packages, or services."""
    return bool(example.dependencies or example.test_dependencies or example.services)


TRANSCRIPT_TEST = "recorded_sample_run"  # tests/test_examples.py: every example has a transcript
# tests/test_live_tools.py: the committed coverage badge is well formed. Like the transcripts it is a
# product of this gate, so the gate must not be blocked by an old copy (a format change would otherwise
# need the file edited by hand before the gate that writes it could run).
BADGE_TEST = "committed_badge_file"


def offline_suite_command() -> list[str]:
    """The whole offline suite, under coverage (the data file the live runs then append to).

    It leaves out the check that transcripts exist: a new example has none until this gate records
    it, so that check runs afterwards (see transcript_command), when `--record` has written them.
    """
    return uv_run(
        None,
        *["python", "-m", "coverage", "run", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        *["-k", f"not {TRANSCRIPT_TEST} and not {BADGE_TEST}"],
    )


def transcript_command(examples: list[Example]) -> list[str]:
    """Check that each example has a sample_run.md matching its current smoke input."""
    names = " or ".join(e.name for e in examples)
    return uv_run(
        None,
        *["pytest", "-q", "-p", "no:cacheprovider", "tests/test_examples.py"],
        *["-k", f"{TRANSCRIPT_TEST} and ({names})"],
    )


GENERIC_TESTS = (
    "tests/test_examples.py",
    "tests/test_content_filter.py",
    "tests/test_cost_limit.py",
    "tests/test_add_agent.py",  # copies the example into a scratch project and tests the copy
)


def offline_command(example: Example) -> list[str]:
    """One example's offline tests, in its isolated environment, appended to the coverage data.

    Includes the generic tests that run every example (smoke flow, labels, content filter, cost
    limits), narrowed to this one by `-k`. In the default environment those tests skip an example
    whose dependencies are missing, so without this they would never run for it at all. Like the
    first stage it leaves out the transcript check, which runs once the example has been recorded.
    """
    return uv_run(
        example,
        *["python", "-m", "coverage", "run", "-a", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        f"examples/{example.name}",
        *GENERIC_TESTS,
        "-k",
        f"{example.name} and not {TRANSCRIPT_TEST}",
        tests=True,
    )


def live_tests_command(example: Example) -> list[str]:
    """One example's real-model tests (`-m eval`), in its isolated environment, with coverage."""
    return uv_run(
        example,
        *[
            "python",
            "-m",
            "coverage",
            "run",
            "-a",
            "-m",
            "pytest",
            "-m",
            "eval",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        f"examples/{example.name}",
        tests=True,
    )


def coverage_command(examples: list[Example]) -> list[str]:
    """Report line coverage of the checked examples' source (100% is required by pyproject)."""
    files = []
    for e in examples:
        files.append(f"examples/{e.name}/agent.py")
        if (e.service_dir / "server.py").is_file():
            files.append(
                f"examples/{e.name}/service/server.py"
            )  # a service's code is example code too
    return uv_run(None, "python", "-m", "coverage", "report", f"--include={','.join(files)}")


def live_command(example: Example, *, record: bool) -> list[str]:
    command = uv_run(example, "python", "scripts/record_example.py", example.name, "--json")
    return command if record else [*command, "--no-write"]


def live_env(example: Example, base: dict[str, str]) -> dict[str, str]:
    """The environment for one example's live run: its budget becomes a hard spend cap.

    Skipped for local models, whose cost Pydantic AI can't compute (the cap couldn't be
    enforced and would only produce a warning), and when the caller set their own cap.
    """
    env = dict(base)
    env.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # keep the startup banner out of captured output
    local = env.get("AGENT_MODEL", "").startswith("ollama:")
    if not local:
        env.setdefault("AGENT_COST_LIMIT", str(example.cost_budget_usd))
    return env


MAX_FAILURE_LINES = 8  # pytest's FAILED lines and assertion details to show; the rest is in the log


def failure_summary(output: str) -> str:
    """What failed, from pytest's output: its `FAILED` summary lines and the assertion details.

    The last lines of a failed pytest run are usually captured log output, which says nothing about
    what went wrong, so look for the failure itself and fall back to the tail only if there is none.
    """
    lines = output.strip().splitlines()
    found = [
        line.strip()
        for line in lines
        if line.startswith(("FAILED ", "ERROR ")) or line.startswith("E   ")
    ]
    return " | ".join((found or lines[-5:])[:MAX_FAILURE_LINES])


def parse_outcome(example: Example, completed: subprocess.CompletedProcess[str]) -> Outcome:
    """The Outcome record_example.py printed, or a failure carrying what the process said."""
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(RESULT_PREFIX):
            return Outcome(**json.loads(line.removeprefix(RESULT_PREFIX)))
    tail = (completed.stderr or completed.stdout).strip().splitlines()[-5:]
    return Outcome(
        example.name,
        "failed",
        error=f"the run produced no result (exit {completed.returncode}): {' | '.join(tail)}",
    )


@dataclass
class Summary:
    text: str
    ok: bool


@dataclass
class Coverage:
    """A gate over the whole run with a report to show: coverage of the examples' source, or that
    each example's transcript exists."""

    ok: bool
    report: str
    title: str = "Coverage of the examples' source:"


def summarize(
    outcomes: list[Outcome],
    *,
    allow_unverified: bool = False,
    coverage: Coverage | None = None,
    transcripts: Coverage | None = None,
) -> Summary:
    lines = [describe(o) for o in outcomes]
    spent = sum(o.cost for o in outcomes if o.cost is not None)
    unpriced = [o.example for o in outcomes if o.status == "passed" and o.cost is None]
    tokens = sum(o.tokens for o in outcomes)
    counts = {s: sum(o.status == s for o in outcomes) for s in ("passed", "failed", "unverified")}
    lines += [
        "",
        f"{counts['passed']} passed, {counts['failed']} failed, {counts['unverified']} unverified"
        f" · {tokens:,} tokens · ${spent:.4f} spent"
        + (f" (no price for: {', '.join(unpriced)})" if unpriced else ""),
    ]
    ok = counts["failed"] == 0 and (counts["unverified"] == 0 or allow_unverified)
    for gate in (coverage, transcripts):
        if gate is not None:
            lines += ["", gate.title, gate.report.strip()]
            ok = ok and gate.ok
    return Summary("\n".join(lines), ok)


def check_examples(
    examples: list[Example],
    *,
    record: bool,
    model: str,
    runner: Runner = run_process,
    env: dict[str, str] | None = None,
    log: Callable[[str], None] = print,
) -> list[Outcome]:
    """Check each example in its own process: offline tests (if isolated), live tests, then the
    live smoke run. A failure at any stage stops that example before the next (paid) stage."""
    base = dict(os.environ if env is None else env)
    outcomes: list[Outcome] = []

    def failed(example: Example, what: str, completed) -> Outcome:
        detail = failure_summary(completed.stdout or completed.stderr)
        return Outcome(example.name, "failed", model=model, error=f"{what}: {detail}")

    def check_one(example: Example, env_for: dict[str, str]) -> Outcome:
        """The three stages for one example, in this environment (which includes any services)."""
        if needs_isolation(example):
            offline = runner(offline_command(example), env_for)
            if offline.returncode != 0:
                return failed(example, "offline tests failed in isolation", offline)
        env_for_example = live_env(example, env_for)
        live_tests = runner(live_tests_command(example), env_for_example)
        if live_tests.returncode != 0:
            return failed(example, "live tests failed", live_tests)
        completed = runner(live_command(example, record=record), env_for_example)
        outcome = parse_outcome(example, completed)
        outcome.model = outcome.model or model
        return outcome

    for example in examples:
        log(f"→ {example.name}")
        if not example.services:
            outcomes.append(check_one(example, base))
            continue
        try:
            # Start the example's docker-compose services, check it against them, and always stop them.
            with running(example, runner, base) as service_env:
                outcomes.append(check_one(example, {**base, **service_env}))
        except ServicesUnavailable as exc:
            outcomes.append(unverified(example, model, str(exc)))
        except ServiceStartError as exc:
            outcomes.append(Outcome(example.name, "failed", model=model, error=str(exc)))
    return outcomes


def transcript_gate(
    examples: list[Example], runner: Runner = run_process, env: dict[str, str] | None = None
) -> Coverage:
    """Fail unless every checked example has a transcript that matches it."""
    run = runner(transcript_command(examples), dict(os.environ if env is None else env))
    return Coverage(
        run.returncode == 0,
        "all present and current" if run.returncode == 0 else (run.stdout or run.stderr)[-1500:],
        title="Recorded runs (sample_run.md):",
    )


def coverage_gate(
    examples: list[Example], runner: Runner = run_process, env: dict[str, str] | None = None
) -> Coverage:
    """Fail unless every line of the examples' source ran in the offline and live tests."""
    report = runner(coverage_command(examples), dict(os.environ if env is None else env))
    return Coverage(report.returncode == 0, (report.stdout or report.stderr))


# --- The coverage badge ---------------------------------------------------------------------

BADGE_PATH = REPO_ROOT / "badges" / "coverage.json"
TOTAL_LINE = re.compile(r"^TOTAL\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)%", re.MULTILINE)


def coverage_percent(report: str) -> float | None:
    """The total from `coverage report`'s output, or None if it has no TOTAL line."""
    match = TOTAL_LINE.search(report)
    return float(match.group(1)) if match else None


def coverage_badge(percent: float) -> dict:
    """The JSON that shields.io's endpoint badge reads: "coverage: 100%"."""
    return {
        "schemaVersion": 1,
        "label": "coverage",
        "message": f"{percent:g}%",
        "color": "brightgreen" if percent >= 100 else "yellow",
    }


def badge_is_earned(
    *, all_examples: bool, measuring: bool, outcomes: Sequence[Outcome], coverage: Coverage | None
) -> bool:
    """Only a complete, clean run may write the badge.

    A subset of the examples, a run without the offline suite, an example that failed or could not
    be checked (no Docker), or a coverage gate that failed would each make the number mean less
    than it says, so none of them may overwrite the last good badge.
    """
    return bool(
        all_examples
        and measuring
        and outcomes
        and all(o.status == "passed" for o in outcomes)
        and coverage is not None
        and coverage.ok
        and coverage_percent(coverage.report) is not None
    )


def write_coverage_badge(coverage: Coverage, path=BADGE_PATH) -> float:
    """Write the badge file from the coverage report; returns the percentage it records."""
    percent = coverage_percent(coverage.report)
    assert percent is not None  # badge_is_earned checked
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(coverage_badge(percent), indent=2) + "\n", encoding="utf-8")
    return percent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("examples", nargs="*", help="example names (default: all)")
    parser.add_argument("--record", action="store_true", help="also refresh each sample_run.md")
    parser.add_argument("--skip-tests", action="store_true", help="skip the offline test suite")
    parser.add_argument(
        "--allow-unverified", action="store_true", help="don't fail on examples needing services"
    )
    args = parser.parse_args(argv)

    if shutil.which("uv") is None:
        print(
            "error: uv is required (each example runs in its own `uv run` environment)",
            file=sys.stderr,
        )
        return 1
    try:
        available = {e.name: e for e in discover(REPO_ROOT / "examples")}
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    unknown = [n for n in args.examples if n not in available]
    if unknown:
        print(
            f"error: unknown example(s) {unknown}; available: {sorted(available)}", file=sys.stderr
        )
        return 1
    selected = [available[n] for n in args.examples] or list(available.values())

    sys.path.insert(0, str(REPO_ROOT))
    try:
        from agent.config import settings  # validates the provider key at import time
    except ValueError as exc:
        print(f"error: the agent model is not configured: {exc}", file=sys.stderr)
        return 1
    print(f"Model: {settings.model}\n")

    measuring = not args.skip_tests
    if measuring:
        print("→ offline test suite (under coverage)")
        run_process(uv_run(None, "python", "-m", "coverage", "erase"), dict(os.environ))
        tests = run_process(offline_suite_command(), dict(os.environ))
        if tests.returncode != 0:
            print((tests.stdout or tests.stderr).strip()[-2000:])
            print("\n✗ the offline tests failed; not running anything live", file=sys.stderr)
            return 1
        print("  passed\n")

    outcomes = check_examples(selected, record=args.record, model=settings.model)
    # Coverage is only meaningful if the offline suite ran under it, so --skip-tests skips it.
    coverage = coverage_gate(selected) if measuring else None
    # After the live stage, which (with --record) is what writes them. An example that could not be
    # checked (no Docker for its services) has no fresh transcript to demand: it is already reported
    # as unverified, which fails the check on its own.
    checked = [e for e, o in zip(selected, outcomes, strict=True) if o.status != "unverified"]
    transcripts = transcript_gate(checked) if checked else None
    summary = summarize(
        outcomes, allow_unverified=args.allow_unverified, coverage=coverage, transcripts=transcripts
    )
    print("\n" + summary.text)
    if summary.ok and badge_is_earned(
        all_examples=not args.examples, measuring=measuring, outcomes=outcomes, coverage=coverage
    ):
        percent = write_coverage_badge(coverage)
        print(
            f"\nWrote {BADGE_PATH.relative_to(REPO_ROOT)} ({percent:g}%): commit it with the release."
        )
    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
