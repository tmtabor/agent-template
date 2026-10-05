"""Helpers for the `test_live.py` files: real-model tests that check an example works.

Those tests are marked `eval` (they call the real model and cost money): run them with
`uv run pytest -m eval examples/<name>`, or all of them through scripts/release_check.py.
"""

import asyncio
import io
import runpy
import sys
from contextlib import redirect_stdout
from types import ModuleType

from tests.agent_finder import module_agents


def every_agent_name(module: ModuleType) -> set[str]:
    """The name of every Agent the module defines (as a variable, or inside a container)."""
    return {agent.name for agent in module_agents(module)}


def assert_every_agent_ran(module: ModuleType, agents_ran: set[str]) -> None:
    """Fail unless each agent the example defines ran, across the runs `agents_ran` unions."""
    missing = every_agent_name(module) - agents_ran
    assert not missing, f"agents that never ran against the real model: {sorted(missing)}"


async def run_as_script(module_name: str) -> str:
    """Run the module's `if __name__ == "__main__"` demo, in process, and return what it printed.

    asyncio.run() inside the demo can't nest in the test's event loop, so it runs on a thread.
    """

    def run() -> str:
        buffer = io.StringIO()
        # runpy warns if the module is already imported (the tests did); set it aside while the
        # demo runs as __main__, then put it back untouched. alter_sys makes the module being
        # run the real `__main__` while it executes, as `python -m` does; without it Pydantic
        # can't resolve forward references in models defined in the demo module.
        imported = sys.modules.pop(module_name, None)
        try:
            with redirect_stdout(buffer):
                runpy.run_module(module_name, run_name="__main__", alter_sys=True)
        finally:
            if imported is not None:
                sys.modules[module_name] = imported
        return buffer.getvalue()

    return await asyncio.to_thread(run)
