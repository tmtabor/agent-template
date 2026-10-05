"""Read and validate `examples/<name>/example.toml`.

Shared by `scripts/add_agent.py` and the example tests. Keep it dependency-free
(standard library only): it must work in a fresh clone and after `--prune`.

Schema — every key but `title`, `pattern`, `summary`, `smoke_input` and
`[entrypoint]` is optional:

    title = "Supervisor / workers"
    pattern = "supervisor"            # category for the index and docs
    summary = "One-line description."
    smoke_input = "Input used by smoke tests and the generated eval starter."
    expected_tools = ["tool_name"]    # tools a real model must call in the live release check
    cost_budget_usd = 0.25            # the live release check fails above this (default 0.25)
    dependencies = ["httpx>=0.28"]    # PEP 508 requirements beyond the template's own
    env = ["SOME_API_KEY"]            # extra environment variables the example needs
    services = ["temporal"]           # external services it needs running
    templated = false                 # true: the example's name is a placeholder to rename

    [entrypoint]
    deps = "SharedDeps"               # deps dataclass (constructible with no arguments)
    run = "run_supervisor"            # async (user_input) -> RunResult helper

    # How smoke tests configure each agent's TestModel, keyed by the agent's variable name.
    # Agents with no entry get the default: a TestModel that calls no tools.
    [smoke.supervisor_agent]
    call_tools = ["delegate_to_analyst"]   # tools to opt in to calling (and then expect called)

    [smoke.extraction_agent]
    output = { name = "Ada", email = "ada@example.com" }   # the output TestModel returns, for
                                                           # agents whose validators reject its junk
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"

REQUIRED = {"title", "pattern", "summary", "smoke_input", "entrypoint"}
OPTIONAL_LISTS = ("expected_tools", "dependencies", "env", "services")
DEFAULT_COST_BUDGET_USD = 0.25
KNOWN = REQUIRED | set(OPTIONAL_LISTS) | {"templated", "smoke", "cost_budget_usd"}
ENTRYPOINT_KEYS = {"deps", "run"}
SMOKE_KEYS = {"call_tools", "output"}

# A loose PEP 508 check: a distribution name, optional extras, optional specifier
# or marker. Enough to catch typos without depending on `packaging`.
REQUIREMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9._,-]+\])?\s*([<>=!~;@].*)?$")


class ManifestError(ValueError):
    """An example.toml is missing, malformed or inconsistent with its directory."""


@dataclass(frozen=True)
class AgentSmoke:
    """How smoke tests configure one agent's TestModel."""

    call_tools: tuple[str, ...] = ()
    output: dict | None = None


@dataclass(frozen=True)
class Example:
    name: str
    path: Path
    title: str
    pattern: str
    summary: str
    smoke_input: str
    deps: str
    run: str
    expected_tools: tuple[str, ...] = ()
    cost_budget_usd: float = DEFAULT_COST_BUDGET_USD
    dependencies: tuple[str, ...] = ()
    env: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    templated: bool = False
    smoke: dict[str, AgentSmoke] = field(default_factory=dict)

    @property
    def module(self) -> str:
        """Import path of the example in place (used by tests)."""
        return f"examples.{self.name}.agent"

    @property
    def source(self) -> Path:
        return self.path / "agent.py"

    @property
    def prompt_files(self) -> list[Path]:
        return sorted((self.path / "prompts").glob("*.txt"))


def _string_list(data: dict, key: str, where: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ManifestError(f"{where}: `{key}` must be a list of non-empty strings")
    return tuple(value)


def _smoke(table: object, where: str) -> dict[str, AgentSmoke]:
    if not isinstance(table, dict):
        raise ManifestError(f"{where}: `smoke` must be a table of [smoke.<agent_variable>] tables")
    result: dict[str, AgentSmoke] = {}
    for agent_name, config in table.items():
        if not agent_name.isidentifier() or not isinstance(config, dict):
            raise ManifestError(f"{where}: [smoke.{agent_name}] must be a table named for an agent")
        unknown = config.keys() - SMOKE_KEYS
        if unknown:
            raise ManifestError(
                f"{where}: [smoke.{agent_name}] has unknown key(s) {sorted(unknown)}"
            )
        output = config.get("output")
        if output is not None and not isinstance(output, dict):
            raise ManifestError(f"{where}: [smoke.{agent_name}] `output` must be a table")
        result[agent_name] = AgentSmoke(
            call_tools=_string_list(config, "call_tools", f"{where} [smoke.{agent_name}]"),
            output=output,
        )
    return result


def load(path: Path) -> Example:
    """Load and validate one example directory."""
    toml_path = path / "example.toml"
    where = str(toml_path)
    if not toml_path.is_file():
        raise ManifestError(f"{where}: missing")
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"{where}: invalid TOML ({exc})") from exc

    missing = REQUIRED - data.keys()
    if missing:
        raise ManifestError(f"{where}: missing key(s) {sorted(missing)}")
    unknown = data.keys() - KNOWN
    if unknown:
        raise ManifestError(f"{where}: unknown key(s) {sorted(unknown)}")
    for key in ("title", "pattern", "summary", "smoke_input"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise ManifestError(f"{where}: `{key}` must be a non-empty string")
    if not isinstance(data.get("templated", False), bool):
        raise ManifestError(f"{where}: `templated` must be true or false")

    entry = data["entrypoint"]
    if not isinstance(entry, dict) or set(entry) != ENTRYPOINT_KEYS:
        raise ManifestError(f"{where}: [entrypoint] must define exactly {sorted(ENTRYPOINT_KEYS)}")
    for key, value in entry.items():
        if not isinstance(value, str) or not value.isidentifier():
            raise ManifestError(f"{where}: entrypoint `{key}` must be a Python identifier")

    smoke = _smoke(data.get("smoke", {}), where)
    budget = data.get("cost_budget_usd", DEFAULT_COST_BUDGET_USD)
    if isinstance(budget, bool) or not isinstance(budget, int | float) or budget <= 0:
        raise ManifestError(f"{where}: `cost_budget_usd` must be a positive number")

    dependencies = _string_list(data, "dependencies", where)
    for requirement in dependencies:
        if not REQUIREMENT_RE.match(requirement):
            raise ManifestError(f"{where}: `{requirement}` is not a valid requirement")

    if not (path / "agent.py").is_file():
        raise ManifestError(f"{path}: missing agent.py")

    return Example(
        name=path.name,
        path=path,
        title=data["title"],
        pattern=data["pattern"],
        summary=data["summary"],
        smoke_input=data["smoke_input"],
        deps=entry["deps"],
        run=entry["run"],
        dependencies=dependencies,
        env=_string_list(data, "env", where),
        services=_string_list(data, "services", where),
        templated=data.get("templated", False),
        smoke=smoke,
        expected_tools=_string_list(data, "expected_tools", where),
        cost_budget_usd=float(budget),
    )


def discover(root: Path = EXAMPLES_DIR) -> list[Example]:
    """Every example under `root`, sorted by name. Raises ManifestError on a bad one."""
    if not root.is_dir():
        return []
    return [
        load(p)
        for p in sorted(root.iterdir())
        if p.is_dir() and not p.name.startswith(("_", ".")) and (p / "example.toml").exists()
    ]
