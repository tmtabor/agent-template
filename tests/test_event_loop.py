"""All async tests share one event loop.

The agents are module-level objects, so the provider's HTTP client is created
inside the first test that uses it and then reused by every later one. With a
per-test event loop (pytest-asyncio's default) that loop is closed by the time
the next test runs, and the next real model call fails with "Event loop is
closed". pyproject.toml pins both loop scopes to "session"; this guards it.
"""

import asyncio

_loops: list[asyncio.AbstractEventLoop] = []


async def test_first_async_test_records_its_loop():
    _loops.append(asyncio.get_running_loop())


async def test_later_async_tests_reuse_that_loop():
    assert _loops, "test_first_async_test_records_its_loop must run first"
    assert asyncio.get_running_loop() is _loops[0]
