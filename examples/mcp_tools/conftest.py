"""A real, local instance of the calendar MCP server, for the offline tests.

The tests talk to it over HTTP exactly as the agent talks to the Docker service, but it is just a
subprocess on a free port: no Docker needed to run the offline suite. (The release check runs the
live tests against the real container.) Needs the server half of fastmcp; without it the tests that
use this fixture are skipped.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

SERVER = Path(__file__).parent / "service" / "server.py"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def accepts_connections(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def server_url() -> Iterator[str]:
    """The URL of a calendar server running locally for the whole test session."""
    try:
        from fastmcp import FastMCP  # noqa: F401 — the server half, not installed by the client
    except ImportError:
        pytest.skip("needs fastmcp-slim[server] to run the server locally")

    port = free_port()
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            [sys.executable, str(SERVER)],
            env={**os.environ, "MCP_PORT": str(port), "MCP_HOST": "127.0.0.1"},
            stdout=subprocess.DEVNULL,
            stderr=errors,
        )
        try:
            deadline = time.monotonic() + 30
            while not accepts_connections(port):
                if process.poll() is not None or time.monotonic() > deadline:
                    errors.seek(0)
                    raise RuntimeError(
                        f"the server did not start: {errors.read().decode()[-1500:]}"
                    )
                time.sleep(0.1)
            yield f"http://127.0.0.1:{port}/mcp"
        finally:
            process.terminate()
            process.wait(timeout=10)
