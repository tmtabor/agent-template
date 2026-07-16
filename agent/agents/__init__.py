"""Canonical names for the chosen agent pattern.

tests/ and evals/ import `run_agent`, `AgentOutput`, `AgentDeps`, and `agent`
from this package rather than from a concrete stub module, so switching
patterns never requires editing them. The import line below is maintained by
`scripts/choose_pattern.py` — run it to pick a pattern and delete the others.
"""

from agent.agents.single import AgentDeps, AgentOutput, agent, run_agent

__all__ = ["AgentDeps", "AgentOutput", "agent", "run_agent"]
