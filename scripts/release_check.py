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
  4. A summary with total tokens and spend. Exits non-zero unless everything passed.

Makes real model calls: needs the provider key for AGENT_MODEL, and costs money (typically well
under a dollar for the whole library on the default model). An example that needs `services`
is reported as unverified, not passed, and fails the check unless --allow-unverified is given.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from example_manifest import REPO_ROOT, Example, ManifestError, discover
from record_example import RESULT_PREFIX, Outcome, describe, unverified

Runner = Callable[[Sequence[str], dict[str, str]], "subprocess.CompletedProcess[str]"]


def uv_run(example: Example | None, *args: str) -> list[str]:
    """`uv run` with the example's declared dependencies layered on, for an isolated run."""
    command = ["uv", "run"]
    if example is not None:
        for requirement in example.dependencies:
            command += ["--with", requirement]
    return [*command, *args]


def offline_suite_command() -> list[str]:
    """The whole offline suite, under coverage (the data file the live runs then append to)."""
    return uv_run(None, "coverage", "run", "-m", "pytest", "-q", "-p", "no:cacheprovider")


def offline_command(example: Example) -> list[str]:
    """One example's offline tests, in its isolated environment, appended to the coverage data."""
    return uv_run(
        example,
        *["coverage", "run", "-a", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        f"examples/{example.name}",
    )


def live_tests_command(example: Example) -> list[str]:
    """One example's real-model tests (`-m eval`), in its isolated environment, with coverage."""
    return uv_run(
        example,
        *["coverage", "run", "-a", "-m", "pytest", "-m", "eval", "-q", "-p", "no:cacheprovider"],
        f"examples/{example.name}",
    )


def coverage_command(examples: list[Example]) -> list[str]:
    """Report line coverage of the checked examples' source (100% is required by pyproject)."""
    include = ",".join(f"examples/{e.name}/agent.py" for e in examples)
    return uv_run(None, "coverage", "report", f"--include={include}")


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
    """The coverage gate: did every line of the checked examples' source run?"""

    ok: bool
    report: str


def summarize(
    outcomes: list[Outcome], *, allow_unverified: bool = False, coverage: Coverage | None = None
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
    if coverage is not None:
        lines += ["", "Coverage of the examples' source:", coverage.report.strip()]
        ok = ok and coverage.ok
    return Summary("\n".join(lines), ok)


def run_process(command: Sequence[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True)


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
        tail = (completed.stdout or completed.stderr).strip().splitlines()[-5:]
        return Outcome(example.name, "failed", model=model, error=f"{what}: {' | '.join(tail)}")

    for example in examples:
        log(f"→ {example.name}")
        if example.services:
            outcomes.append(unverified(example, model))
            continue
        if example.dependencies:
            offline = runner(offline_command(example), base)
            if offline.returncode != 0:
                outcomes.append(failed(example, "offline tests failed in isolation", offline))
                continue
        env_for_example = live_env(example, base)
        live_tests = runner(live_tests_command(example), env_for_example)
        if live_tests.returncode != 0:
            outcomes.append(failed(example, "live tests failed", live_tests))
            continue
        completed = runner(live_command(example, record=record), env_for_example)
        outcome = parse_outcome(example, completed)
        outcome.model = outcome.model or model
        outcomes.append(outcome)
    return outcomes


def coverage_gate(
    examples: list[Example], runner: Runner = run_process, env: dict[str, str] | None = None
) -> Coverage:
    """Fail unless every line of the examples' source ran in the offline and live tests."""
    report = runner(coverage_command(examples), dict(os.environ if env is None else env))
    return Coverage(report.returncode == 0, (report.stdout or report.stderr))


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
        run_process(uv_run(None, "coverage", "erase"), dict(os.environ))
        tests = run_process(offline_suite_command(), dict(os.environ))
        if tests.returncode != 0:
            print((tests.stdout or tests.stderr).strip()[-2000:])
            print("\n✗ the offline tests failed; not running anything live", file=sys.stderr)
            return 1
        print("  passed\n")

    outcomes = check_examples(selected, record=args.record, model=settings.model)
    # Coverage is only meaningful if the offline suite ran under it, so --skip-tests skips it.
    coverage = coverage_gate(selected) if measuring else None
    summary = summarize(outcomes, allow_unverified=args.allow_unverified, coverage=coverage)
    print("\n" + summary.text)
    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
