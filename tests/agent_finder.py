"""Find the Agent instances a module holds. Shared by the safety net and the example tests."""

from types import ModuleType

from pydantic_ai import Agent


def agents_in(value) -> list[Agent]:
    """The Agent(s) a module-level value holds: itself, or a dict/list/tuple/set of them."""
    if isinstance(value, Agent):
        return [value]
    if isinstance(value, dict):
        value = value.values()
    if isinstance(value, list | tuple | set | frozenset | type({}.values())):
        return [v for v in value if isinstance(v, Agent)]
    return []


def module_agents(module: ModuleType) -> list[Agent]:
    """Every distinct Agent the module holds, as variables or inside containers."""
    seen: dict[int, Agent] = {}
    for value in vars(module).values():
        for found in agents_in(value):
            seen.setdefault(id(found), found)
    return list(seen.values())
