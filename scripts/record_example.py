#!/usr/bin/env python3
"""Run examples against the real model, check them, and write their sample_run.md.

Usage:
    uv run python scripts/record_example.py router
    uv run python scripts/record_example.py --all
    uv run python scripts/record_example.py router --no-write     # check only, keep the old transcript

Makes real model calls (needs the provider key for AGENT_MODEL; costs money). A run that fails
its checks never overwrites the existing sample_run.md. For the full pre-release gate — the
offline tests, isolated environments, a spend summary — use scripts/release_check.py.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from example_manifest import REPO_ROOT, Example, ManifestError, discover

sys.path.insert(0, str(REPO_ROOT))  # so `agent` and `examples` import when run as a script

from live_run import LiveRun, render_transcript, run_live, verify  # noqa: E402

RESULT_PREFIX = "RESULT_JSON:"  # release_check.py reads this line from the subprocess's output


@dataclass
class Outcome:
    """What happened to one example."""

    example: str
    status: str  # "passed" | "failed" | "unverified"
    model: str = ""
    failures: list[str] = field(default_factory=list)
    error: str | None = None
    steps: int = 0
    tokens: int = 0
    cost: float | None = None
    duration_s: float = 0.0
    transcript: str | None = None

    def to_json(self) -> str:
        return RESULT_PREFIX + json.dumps(asdict(self))


def transcript_path(example: Example) -> Path:
    return example.path / "sample_run.md"


async def record_one(example: Example, run, model: str, *, write: bool = True) -> Outcome:
    """Run one example live, verify it, and (if it passed) write its transcript."""
    try:
        live: LiveRun = await run_live(example, run, model)
    except Exception as exc:  # a failed example must not stop the others; report why
        return Outcome(example.name, "failed", model=model, error=f"{type(exc).__name__}: {exc}")

    failures = verify(live)
    outcome = Outcome(
        example.name,
        "failed" if failures else "passed",
        model=model,
        failures=failures,
        steps=len(live.result.steps),
        tokens=live.tokens,
        cost=float(live.cost) if live.cost is not None else None,
        duration_s=round(live.duration_s, 2),
    )
    if write and not failures:
        path = transcript_path(example)
        path.write_text(render_transcript(live), encoding="utf-8")
        outcome.transcript = str(
            path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        )
    return outcome


def unverified(example: Example, model: str, reason: str | None = None) -> Outcome:
    """An example that could not be checked, and why: never counted as passed."""
    return Outcome(
        example.name,
        "unverified",
        model=model,
        error=reason
        or f"needs its services running ({', '.join(example.services)}); "
        "scripts/release_check.py starts them with Docker",
    )


def services_are_running(example: Example) -> bool:
    """Whether the release check has started this example's services and told us where they are."""
    return all(os.environ.get(spec.env) for spec in example.service_specs.values())


async def record_all(examples: list[Example], model: str, *, write: bool) -> list[Outcome]:
    """Run each example in turn on one event loop (module-level agents bind an HTTP client to
    the loop that first uses them, so one loop for all of them)."""
    outcomes = []
    for example in examples:
        if not services_are_running(example):
            outcomes.append(unverified(example, model))
            continue
        try:
            run = getattr(importlib.import_module(example.module), example.run)
        except ModuleNotFoundError as exc:
            outcomes.append(
                Outcome(example.name, "failed", model=model, error=f"missing dependency: {exc}")
            )
            continue
        outcomes.append(await record_one(example, run, model, write=write))
    return outcomes


ICONS = {"passed": "✓", "failed": "✗", "unverified": "?"}


def describe(outcome: Outcome) -> str:
    detail = outcome.error or "; ".join(outcome.failures)
    if outcome.status == "passed":
        cost = f"${outcome.cost:.4f}" if outcome.cost is not None else "cost unknown"
        detail = f"{outcome.steps} steps, {outcome.tokens:,} tokens, {cost}, {outcome.duration_s}s"
        if outcome.transcript:
            detail += f" → {outcome.transcript}"
    return f"{ICONS[outcome.status]} {outcome.example:<20} {detail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("examples", nargs="*", help="example names to run")
    parser.add_argument("--all", action="store_true", help="run every example")
    parser.add_argument("--no-write", action="store_true", help="check only; write no transcript")
    parser.add_argument("--json", action="store_true", help="print machine-readable results too")
    args = parser.parse_args(argv)

    try:
        available = {e.name: e for e in discover(REPO_ROOT / "examples")}
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.all == bool(args.examples):
        parser.error("name one or more examples, or pass --all")
    unknown = [n for n in args.examples if n not in available]
    if unknown:
        print(
            f"error: unknown example(s) {unknown}; available: {sorted(available)}", file=sys.stderr
        )
        return 1
    selected = list(available.values()) if args.all else [available[n] for n in args.examples]

    try:
        from agent.config import settings  # validates the provider key at import time
    except ValueError as exc:
        print(f"error: the agent model is not configured: {exc}", file=sys.stderr)
        return 1

    outcomes = asyncio.run(record_all(selected, settings.model, write=not args.no_write))
    for outcome in outcomes:
        print(describe(outcome))
        if args.json:
            print(outcome.to_json())
    return 0 if all(o.status == "passed" for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
