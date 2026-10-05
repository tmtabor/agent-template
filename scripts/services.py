"""Start and stop the docker-compose services an example needs, for the release check.

An example that needs a running service (an MCP server, a Temporal server) declares it in
example.toml and ships `service/docker-compose.yml`:

    services = ["mcp-server"]
    [service.mcp-server]
    port = 8000                  # the container port, published to a free port on 127.0.0.1
    env = "MCP_SERVER_URL"       # where the example reads the address from
    url = "http://{address}/mcp"

`running(example)` starts them (`docker compose up --build --wait`, so it returns once the compose
healthchecks pass), looks up the host port Docker chose for each, and yields the environment
variables that tell the example where its services are. It always tears them down afterwards. If
Docker isn't usable it raises `ServicesUnavailable`, which the release check reports as *unverified*
rather than passed; if a service won't start it raises `ServiceStartError` with the container logs.

Every call goes through an injectable `runner`, so the logic is tested without Docker.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

from example_manifest import REPO_ROOT, Example

Runner = Callable[[Sequence[str], dict[str, str]], "subprocess.CompletedProcess[str]"]

START_TIMEOUT_SECONDS = 180  # image builds and pulls on a cold machine take a while


class ServicesUnavailable(Exception):
    """Docker isn't usable here, so the example's services can't be started."""


class ServiceStartError(Exception):
    """A service failed to build, start, or become healthy."""


def run_process(command: Sequence[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    except FileNotFoundError as exc:  # the program (docker) isn't installed
        return subprocess.CompletedProcess(list(command), 127, "", str(exc))


def project_name(example: Example) -> str:
    """A compose project name that can't collide with the user's own stacks or a parallel run."""
    return re.sub(r"[^a-z0-9_-]", "-", f"agent-template-{example.name}-{os.getpid()}".lower())


def compose(example: Example, project: str, *args: str) -> list[str]:
    return ["docker", "compose", "-f", str(example.compose_file), "-p", project, *args]


def docker_unavailable(runner: Runner, env: dict[str, str]) -> str | None:
    """Why Docker can't be used, or None if it can (the daemon is running and Compose exists)."""
    daemon = runner(["docker", "info"], env)
    if daemon.returncode != 0:
        detail = (daemon.stderr or daemon.stdout).strip().splitlines()
        return "Docker is not available: " + (detail[-1] if detail else "`docker info` failed")
    if runner(["docker", "compose", "version"], env).returncode != 0:
        return "Docker Compose is not available"
    return None


def host_address(docker_output: str) -> str:
    """`127.0.0.1:55012` from `docker compose port`'s output; a wildcard host becomes 127.0.0.1."""
    line = docker_output.strip().splitlines()[0]
    host, _, port = line.rpartition(":")
    if host in {"", "0.0.0.0", "::", "[::]"}:
        host = "127.0.0.1"
    return f"{host}:{port}"


def start(example: Example, project: str, runner: Runner, env: dict[str, str]) -> dict[str, str]:
    """Bring the services up and return the environment that locates them."""
    up = runner(
        compose(
            example,
            project,
            "up",
            "-d",
            "--build",
            "--wait",
            "--wait-timeout",
            str(START_TIMEOUT_SECONDS),
        ),
        env,
    )
    if up.returncode != 0:
        logs = runner(compose(example, project, "logs", "--tail", "30"), env)
        detail = (logs.stdout or up.stderr or up.stdout).strip()
        raise ServiceStartError(f"{', '.join(example.services)} did not start: {detail[-1500:]}")

    located: dict[str, str] = {}
    for spec in example.service_specs.values():
        found = runner(compose(example, project, "port", spec.name, str(spec.port)), env)
        if found.returncode != 0 or not found.stdout.strip():
            raise ServiceStartError(
                f"{spec.name} is running but port {spec.port} is not published: {found.stderr.strip()}"
            )
        located[spec.env] = spec.url.format(address=host_address(found.stdout))
    return located


def stop(example: Example, project: str, runner: Runner, env: dict[str, str]) -> None:
    """Tear everything down: containers, networks, volumes and the images this project built.

    `--rmi local` matters because every run uses a fresh project name, so without it each run would
    leave a new image behind. Docker's layer cache is untouched, so the next build is still fast.
    Best effort: it must never mask the real result.
    """
    runner(compose(example, project, "down", "-v", "--remove-orphans", "--rmi", "local"), env)


@contextmanager
def running(
    example: Example, runner: Runner = run_process, env: dict[str, str] | None = None
) -> Iterator[dict[str, str]]:
    """Run the example's services for the duration of the block, yielding their environment.

    Raises ServicesUnavailable before touching anything if Docker isn't usable. Once it has begun
    to start anything it always runs `down`, even if starting failed halfway or the block raised.
    """
    env = dict(os.environ if env is None else env)
    reason = docker_unavailable(runner, env)
    if reason:
        raise ServicesUnavailable(reason)

    project = project_name(example)
    try:
        yield start(example, project, runner, env)
    finally:
        stop(example, project, runner, env)
