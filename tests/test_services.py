"""Starting and stopping an example's docker-compose services, and how the release check uses them.

Everything goes through an injected runner, so no Docker daemon is needed: the fake plays Docker's
part, and the tests check what was run, in what order, and that teardown always happens.
"""

import dataclasses
from pathlib import Path

import pytest

import services
from example_manifest import ManifestError, load
from release_check import check_examples
from services import ServiceStartError, ServicesUnavailable
from tests.examples_support import EXAMPLES
from tests.test_live_tools import FakeRunner, completed, stage_of


def example(name: str = "mcp_tools"):
    return next(e for e in EXAMPLES if e.name == name)


ENV: dict[str, str] = {"PATH": "x"}


class FakeDocker(FakeRunner):
    """The release check's fake runner, plus the part of Docker the services module talks to."""

    def __init__(
        self,
        *,
        daemon: bool = True,
        compose: bool = True,
        up_ok: bool = True,
        port: str = "127.0.0.1:55012\n",
        fail: str | None = None,
    ):
        super().__init__(fail=fail)
        self.daemon, self.compose, self.up_ok, self.port = daemon, compose, up_ok, port

    @property
    def docker_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[0] == "docker"]

    @property
    def verbs(self) -> list[str]:
        """What was asked of Docker: info, version, up, port, logs, down."""
        out = []
        for c in self.docker_calls:
            out.append(
                c[1]
                if c[1] == "info"
                else "version"
                if c[2] == "version"
                else next(v for v in ("up", "port", "logs", "down") if v in c)
            )
        return out

    @property
    def stages(self) -> list[str]:  # the release check's own stages, without Docker's
        return [stage_of(c) for c, _ in self.calls if c[0] != "docker"]

    def __call__(self, command, env):
        if command[0] != "docker":
            return super().__call__(command, env)
        self.calls.append((list(command), env))
        if command[1] == "info":
            return completed(
                "",
                0 if self.daemon else 1,
                "" if self.daemon else "Cannot connect to the Docker daemon",
            )
        if command[2] == "version":
            return completed("", 0 if self.compose else 1)
        if "up" in command:
            return completed("", 0 if self.up_ok else 1, "" if self.up_ok else "build failed")
        if "port" in command:
            return completed(self.port, 0 if self.port else 1, "" if self.port else "no port")
        if "logs" in command:
            return completed("mcp-server-1  | Traceback: boom")
        return completed("")  # down


# --- Small pieces ---


@pytest.mark.parametrize(
    ("docker_says", "address"),
    [
        ("127.0.0.1:55012\n", "127.0.0.1:55012"),
        ("0.0.0.0:55012\n[::]:55012\n", "127.0.0.1:55012"),  # a wildcard host becomes loopback
        (":::4567", "127.0.0.1:4567"),
        ("[::]:4567", "127.0.0.1:4567"),
        ("192.168.1.9:8080", "192.168.1.9:8080"),
    ],
)
def test_the_host_address_is_read_from_dockers_port_output(docker_says, address):
    assert services.host_address(docker_says) == address


def test_the_compose_project_name_is_safe_and_unique_to_the_run():
    name = services.project_name(example())
    assert name.startswith("agent-template-mcp_tools-") and name == name.lower()
    assert all(c.isalnum() or c in "_-" for c in name)


def test_a_missing_docker_program_is_a_normal_result_not_a_crash():
    result = services.run_process(["definitely-not-a-real-program-xyz"], ENV)
    assert result.returncode == 127


def test_docker_is_usable_when_the_daemon_and_compose_both_answer():
    assert services.docker_unavailable(FakeDocker(), ENV) is None


def test_a_stopped_daemon_is_explained():
    reason = services.docker_unavailable(FakeDocker(daemon=False), ENV)
    assert reason == "Docker is not available: Cannot connect to the Docker daemon"


def test_a_daemon_that_says_nothing_still_gets_a_reason():
    silent = lambda command, env: completed("", 1)  # noqa: E731
    assert (
        services.docker_unavailable(silent, ENV) == "Docker is not available: `docker info` failed"
    )


def test_missing_compose_is_explained():
    assert (
        services.docker_unavailable(FakeDocker(compose=False), ENV)
        == "Docker Compose is not available"
    )


# --- start / stop / running ---


def test_start_builds_waits_for_health_and_reports_where_each_service_is():
    docker = FakeDocker()
    located = services.start(example(), "proj", docker, ENV)

    up = next(c for c in docker.docker_calls if "up" in c)
    assert {"-d", "--build", "--wait"} <= set(up) and "--wait-timeout" in up
    assert up[up.index("-p") + 1] == "proj" and up[up.index("-f") + 1].endswith(
        "service/docker-compose.yml"
    )
    assert located == {"MCP_SERVER_URL": "http://127.0.0.1:55012/mcp"}


def test_a_service_that_will_not_start_fails_with_its_logs():
    docker = FakeDocker(up_ok=False)
    with pytest.raises(ServiceStartError, match="mcp-server did not start.*Traceback: boom"):
        services.start(example(), "proj", docker, ENV)


def test_a_service_whose_port_is_not_published_is_an_error():
    with pytest.raises(ServiceStartError, match="port 8000 is not published"):
        services.start(example(), "proj", FakeDocker(port=""), ENV)


def test_running_yields_the_environment_and_always_tears_down():
    docker = FakeDocker()
    with services.running(example(), docker, ENV) as env:
        assert env == {"MCP_SERVER_URL": "http://127.0.0.1:55012/mcp"}
        assert docker.verbs[-1] != "down"  # still up while the block runs
    assert docker.verbs == ["info", "version", "up", "port", "down"]
    down = docker.docker_calls[-1]
    assert {"-v", "--remove-orphans"} <= set(down)  # volumes and strays go too
    assert (
        down[down.index("--rmi") + 1] == "local"
    )  # and the image this run built, so none accumulate


def test_teardown_happens_even_when_the_block_raises():
    docker = FakeDocker()
    with pytest.raises(ZeroDivisionError), services.running(example(), docker, ENV):
        raise ZeroDivisionError
    assert docker.verbs[-1] == "down"


def test_teardown_happens_even_when_starting_failed_halfway():
    docker = FakeDocker(up_ok=False)
    with pytest.raises(ServiceStartError), services.running(example(), docker, ENV):
        pytest.fail("the block must not run if the service did not start")
    assert docker.verbs[-1] == "down"  # a half-built stack is not left behind


def test_without_docker_nothing_is_started_and_nothing_needs_stopping():
    docker = FakeDocker(daemon=False)
    with (
        pytest.raises(ServicesUnavailable, match="Docker is not available"),
        services.running(example(), docker, ENV),
    ):
        pytest.fail("the block must not run")
    assert docker.verbs == ["info"]  # it never tried to start, so there is nothing to tear down


# --- The release check, with services ---


def check(runner, **kwargs):
    return check_examples(
        [example()],
        record=False,
        model="m",
        runner=runner,
        env=dict(ENV),
        log=lambda _: None,
        **kwargs,
    )


def test_an_example_with_services_is_checked_against_them_with_their_address_in_its_environment():
    docker = FakeDocker()
    (outcome,) = check(docker)

    assert outcome.status == "passed"
    # Started first, checked in isolation then live, stopped last.
    assert docker.verbs == ["info", "version", "up", "port", "down"]
    assert docker.stages == ["offline", "live_tests", "smoke"]
    for command, env in docker.calls:
        if command[0] != "docker":
            assert env["MCP_SERVER_URL"] == "http://127.0.0.1:55012/mcp"  # every stage can find it


def test_the_services_are_up_for_every_stage_and_down_only_after_the_last():
    docker = FakeDocker()
    check(docker)
    commands = [c for c, _ in docker.calls]
    first_stage = next(i for i, c in enumerate(commands) if c[0] != "docker")
    last_stage = max(i for i, c in enumerate(commands) if c[0] != "docker")
    up = next(i for i, c in enumerate(commands) if c[0] == "docker" and "up" in c)
    down = next(i for i, c in enumerate(commands) if c[0] == "docker" and "down" in c)
    assert up < first_stage and last_stage < down


def test_without_docker_the_example_is_unverified_with_the_reason_and_nothing_runs():
    docker = FakeDocker(daemon=False)
    (outcome,) = check(docker)
    assert outcome.status == "unverified" and "Docker is not available" in outcome.error
    assert docker.stages == []  # no test of any kind ran, and nothing was recorded or spent


def test_a_service_that_fails_to_start_fails_the_example_and_cleans_up():
    docker = FakeDocker(up_ok=False)
    (outcome,) = check(docker)
    assert outcome.status == "failed" and "did not start" in outcome.error
    assert docker.stages == [] and docker.verbs[-1] == "down"


def test_a_failing_check_still_stops_the_services():
    docker = FakeDocker(fail="live_tests")
    (outcome,) = check(docker)
    assert outcome.status == "failed" and "live tests failed" in outcome.error
    assert docker.stages == ["offline", "live_tests"] and docker.verbs[-1] == "down"


def test_the_transcript_check_covers_services_examples_that_were_verified_and_skips_unverified_ones():
    """Regression: examples with services were once excluded outright, leaving the check empty."""
    from release_check import transcript_command

    command = transcript_command([example("mcp_tools"), example("router")])
    assert command[-1] == "recorded_sample_run and (mcp_tools or router)"


def test_an_example_without_services_never_touches_docker():
    docker = FakeDocker()
    router = next(e for e in EXAMPLES if e.name == "router")
    (outcome,) = check_examples(
        [router], record=False, model="m", runner=docker, env=dict(ENV), log=lambda _: None
    )
    assert outcome.status == "passed" and docker.docker_calls == []


def test_the_isolated_stage_also_applies_to_an_example_that_only_needs_a_service_or_test_packages():
    from release_check import needs_isolation

    assert needs_isolation(example())  # test dependencies and a service
    assert not needs_isolation(next(e for e in EXAMPLES if e.name == "router"))
    assert needs_isolation(dataclasses.replace(example("router"), dependencies=("httpx",)))


def test_test_dependencies_are_layered_on_for_tests_but_not_for_the_smoke_run():
    from release_check import live_command, live_tests_command, offline_command

    tests_with = [c for c in live_tests_command(example()) if c.startswith("fastmcp")]
    assert tests_with == [
        "fastmcp-slim[server]>=4.0,<5"
    ]  # the live tests start the server's tooling
    assert any(c.startswith("fastmcp") for c in offline_command(example()))
    # Using the agent needs nothing extra, so the recorded run is made without it.
    assert not any(c.startswith("fastmcp") for c in live_command(example(), record=True))


# --- record_example, run on its own ---


def test_an_example_with_services_is_unverified_unless_the_release_check_started_them(monkeypatch):
    import record_example

    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    assert not record_example.services_are_running(example())
    outcome = record_example.unverified(example(), "m")
    assert (
        outcome.status == "unverified"
        and "release_check.py starts them with Docker" in outcome.error
    )

    monkeypatch.setenv("MCP_SERVER_URL", "http://127.0.0.1:1/mcp")
    assert record_example.services_are_running(example())
    router = next(e for e in EXAMPLES if e.name == "router")
    assert record_example.services_are_running(router)  # nothing to wait for


# --- The manifest ---

VALID = """
title = "x"
pattern = "x"
summary = "x"
smoke_input = "x"
services = ["svc"]
[entrypoint]
deps = "D"
run = "r"
"""


def make_example(tmp_path: Path, body: str, compose: bool = True) -> Path:
    (tmp_path / "agent.py").write_text("")
    (tmp_path / "example.toml").write_text(body)
    if compose:
        (tmp_path / "service").mkdir()
        (tmp_path / "service" / "docker-compose.yml").write_text("services: {}\n")
    return tmp_path


def test_a_service_declaration_is_read(tmp_path: Path):
    loaded = load(
        make_example(
            tmp_path,
            VALID + '\n[service.svc]\nport = 8000\nenv = "SVC_URL"\nurl = "http://{address}/x"\n',
        )
    )
    spec = loaded.service_specs["svc"]
    assert (spec.port, spec.env, spec.url) == (8000, "SVC_URL", "http://{address}/x")
    assert loaded.compose_file == tmp_path / "service" / "docker-compose.yml"


def test_the_address_template_defaults_to_the_bare_address(tmp_path: Path):
    loaded = load(
        make_example(tmp_path, VALID + '\n[service.svc]\nport = 7233\nenv = "TEMPORAL_ADDRESS"\n')
    )
    assert loaded.service_specs["svc"].url == "{address}"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (VALID, "each listed service needs a"),  # listed but not described
        (
            VALID.replace('services = ["svc"]\n', "") + '[service.svc]\nport = 1\nenv = "A"\n',
            "each listed service needs a",
        ),
        (VALID + '[service.svc]\nport = 0\nenv = "A"\n', "port number"),
        (VALID + '[service.svc]\nport = "http"\nenv = "A"\n', "port number"),
        (VALID + '[service.svc]\nport = 80\nenv = "not valid"\n', "environment variable name"),
        (
            VALID + '[service.svc]\nport = 80\nenv = "A"\nurl = "http://nowhere"\n',
            r"must contain \{address\}",
        ),
        (VALID + "[service.svc]\nport = 80\n", "needs `port` and `env`"),
        (VALID + '[service.svc]\nport = 80\nenv = "A"\nbogus = 1\n', "needs `port` and `env`"),
    ],
)
def test_an_invalid_service_declaration_is_rejected(tmp_path: Path, body: str, message: str):
    with pytest.raises(ManifestError, match=message):
        load(make_example(tmp_path, body))


def test_a_service_without_a_compose_file_is_rejected(tmp_path: Path):
    body = VALID + '[service.svc]\nport = 80\nenv = "A"\n'
    with pytest.raises(ManifestError, match="no service/docker-compose.yml"):
        load(make_example(tmp_path, body, compose=False))


def test_service_must_be_a_table(tmp_path: Path):
    body = "service = 3\n" + VALID
    with pytest.raises(ManifestError, match="must be a table"):
        load(make_example(tmp_path, body))


@pytest.mark.parametrize("name", sorted({e.name for e in EXAMPLES if e.services}))
def test_a_compose_file_publishes_to_localhost_only_and_has_a_healthcheck(name):
    """What the release check relies on: `up --wait` needs a healthcheck, and a published port must not
    be exposed beyond this machine."""
    ex = example(name)
    text = ex.compose_file.read_text()
    for spec in ex.service_specs.values():
        assert spec.name in text
        assert f'"127.0.0.1::{spec.port}"' in text  # loopback only, with a host port Docker picks
    assert "healthcheck:" in text
    assert (ex.service_dir / "Dockerfile").is_file()
