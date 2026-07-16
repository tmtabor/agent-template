#!/usr/bin/env python3
"""Pick an agent pattern: keep one stub, delete the others, rewire imports.

Usage:
    uv run python scripts/choose_pattern.py {single|supervisor|tool_calling}

Deletes the two unchosen stub files from agent/agents/ and rewrites the
canonical import line in agent/agents/__init__.py so tests/ and evals/
keep working with zero manual edits. Run it once, right after cloning.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agent" / "agents"
INIT_FILE = AGENTS_DIR / "__init__.py"

# Canonical import line per pattern — keep in sync with the stubs' exports.
IMPORTS = {
    "single": "from agent.agents.single import AgentDeps, AgentOutput, agent, run_agent",
    "supervisor": (
        "from agent.agents.supervisor import (\n"
        "    SharedDeps as AgentDeps,\n"
        "    SupervisorOutput as AgentOutput,\n"
        "    run_supervisor as run_agent,\n"
        "    supervisor_agent as agent,\n"
        ")"
    ),
    "tool_calling": (
        "from agent.agents.tool_calling import (\n"
        "    ToolAgentDeps as AgentDeps,\n"
        "    ToolAgentOutput as AgentOutput,\n"
        "    run_tool_agent as run_agent,\n"
        "    tool_agent as agent,\n"
        ")"
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pattern", choices=sorted(IMPORTS), help="the agent pattern to keep")
    chosen = parser.parse_args().pattern

    missing = [p for p in IMPORTS if not (AGENTS_DIR / f"{p}.py").exists()]
    if missing:
        print(f"error: stub file(s) already deleted: {', '.join(missing)}", file=sys.stderr)
        print("A pattern was already chosen — nothing to do.", file=sys.stderr)
        return 1

    init_text = INIT_FILE.read_text(encoding="utf-8")
    if IMPORTS["single"] not in init_text:
        print(f"error: expected canonical import line not found in {INIT_FILE}", file=sys.stderr)
        print("Has agent/agents/__init__.py been edited by hand?", file=sys.stderr)
        return 1

    INIT_FILE.write_text(init_text.replace(IMPORTS["single"], IMPORTS[chosen]), encoding="utf-8")
    print(f"Rewired agent/agents/__init__.py to {chosen}")

    for pattern in IMPORTS:
        if pattern != chosen:
            (AGENTS_DIR / f"{pattern}.py").unlink()
            print(f"Deleted agent/agents/{pattern}.py")

    print(f"\nDone — the {chosen} pattern is active. `uv run pytest` should pass as-is.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
