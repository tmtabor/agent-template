"""Example agents. Browse them, run them in place, or copy one into your project.

Each subdirectory is one pattern, described by its `example.toml`. Add one to
your project with `scripts/add_agent.py`; don't import from here in app code.
Importing this package registers each example's prompt directory with
`load_prompt`, so an example runs in place exactly as its copy will.
"""

from pathlib import Path

from agent.prompts.templates import PROMPTS_DIRS

for _prompts in sorted(Path(__file__).parent.glob("*/prompts")):
    if _prompts not in PROMPTS_DIRS:
        PROMPTS_DIRS.append(_prompts)
