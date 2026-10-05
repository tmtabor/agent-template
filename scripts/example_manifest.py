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
    test_dependencies = ["x"]         # extra packages its *tests* need, which add_agent.py does not
                                      # install into your project (e.g. a server run in the tests)
    env = ["SOME_API_KEY"]            # extra environment variables the example needs
    services = ["mcp-server"]         # docker-compose services it needs running (service/)
    templated = false                 # true: the example's name is a placeholder to rename

    # One table per entry in `services`: how the release check finds the service once Docker has
    # started it. The compose file is service/docker-compose.yml, and should publish the container
    # port on 127.0.0.1 with a free host port ("127.0.0.1::8000").
    [service.mcp-server]
    port = 8000                       # the container port the service listens on
    env = "MCP_SERVER_URL"            # the environment variable the example reads its address from
    url = "http://{address}/mcp"      # how the host:port address becomes that value

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
OPTIONAL_LISTS = ("expected_tools", "dependencies", "test_dependencies", "env", "services")
DEFAULT_COST_BUDGET_USD = 0.25
KNOWN = REQUIRED | set(OPTIONAL_LISTS) | {"templated", "smoke", "cost_budget_usd", "service"}
SERVICE_KEYS = {"port", "env", "url"}
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
class ServiceSpec:
    """How to find one docker-compose service once it is running."""

    name: str
    port: int  # the container port it listens on, published by the compose file
    env: str  # the environment variable the example reads the service's address from
    url: str = "{address}"  # a template for that value; {address} is the host:port Docker chose


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
    service_specs: dict[str, ServiceSpec] = field(default_factory=dict)
    test_dependencies: tuple[str, ...] = ()
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
    def service_dir(self) -> Path:
        """The service's own files (server, Dockerfile, compose file), if the example has any."""
        return self.path / "service"

    @property
    def compose_file(self) -> Path:
        return self.service_dir / "docker-compose.yml"

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


def _services(data: dict, names: tuple[str, ...], path: Path, where: str) -> dict[str, ServiceSpec]:
    tables = data.get("service", {})
    if not isinstance(tables, dict):
        raise ManifestError(f"{where}: `service` must be a table of [service.<name>] tables")
    if set(tables) != set(names):
        raise ManifestError(
            f"{where}: `services` lists {sorted(names)} but [service.*] describes {sorted(tables)}; "
            "each listed service needs a [service.<name>] table and vice versa"
        )
    specs: dict[str, ServiceSpec] = {}
    for name, table in tables.items():
        if (
            not isinstance(table, dict)
            or set(table) - SERVICE_KEYS
            or not {"port", "env"} <= set(table)
        ):
            raise ManifestError(
                f"{where}: [service.{name}] needs `port` and `env` (and may set `url`)"
            )
        port, env = table["port"], table["env"]
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
            raise ManifestError(f"{where}: [service.{name}] `port` must be a port number")
        if not isinstance(env, str) or not env.isidentifier():
            raise ManifestError(
                f"{where}: [service.{name}] `env` must be an environment variable name"
            )
        url = table.get("url", "{address}")
        if not isinstance(url, str) or "{address}" not in url:
            raise ManifestError(f"{where}: [service.{name}] `url` must contain {{address}}")
        specs[name] = ServiceSpec(name, port, env, url)
    if specs and not (path / "service" / "docker-compose.yml").is_file():
        raise ManifestError(f"{path}: declares services but has no service/docker-compose.yml")
    return specs


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
    test_dependencies = _string_list(data, "test_dependencies", where)
    for requirement in (*dependencies, *test_dependencies):
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
        service_specs=_services(data, _string_list(data, "services", where), path, where),
        test_dependencies=test_dependencies,
        templated=data.get("templated", False),
        smoke=smoke,
        expected_tools=_string_list(data, "expected_tools", where),
        cost_budget_usd=float(budget),
    )


# How examples are listed in the docs and the examples index: single agents first, then the
# multi-agent patterns, simplest to most involved. A new example not named here is appended
# alphabetically, so adding one never breaks anything; add it here to place it deliberately.
DISPLAY_ORDER = [
    "blank",
    "single",
    "tool_calling",
    "extraction",
    "rag",
    "mcp_tools",
    "code_mode",
    "temporal",
    "conversation",
    "human_in_the_loop",
    "guardrails",
    "supervisor",
    "router",
    "pipeline",
    "fan_out",
    "evaluator_optimizer",
]


def display_order(examples: list[Example]) -> list[Example]:
    """`examples` in DISPLAY_ORDER, with any unlisted ones after, alphabetically."""
    rank = {name: i for i, name in enumerate(DISPLAY_ORDER)}
    return sorted(examples, key=lambda e: (rank.get(e.name, len(rank)), e.name))


def discover(root: Path = EXAMPLES_DIR) -> list[Example]:
    """Every example under `root`, sorted by name. Raises ManifestError on a bad one."""
    if not root.is_dir():
        return []
    return [
        load(p)
        for p in sorted(root.iterdir())
        if p.is_dir() and not p.name.startswith(("_", ".")) and (p / "example.toml").exists()
    ]
