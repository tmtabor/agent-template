"""Fixtures for tests that live inside examples/.

Settings validates the provider key at import time, and tests/conftest.py (which sets dummy
keys for the unit tests) is not loaded when you run just `pytest examples/<name>`. A dummy key
spends nothing: these tests override the model, and a call that escaped would fail to
authenticate rather than bill.
"""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "unit-test-dummy-key")
os.environ.setdefault("OPENAI_API_KEY", "unit-test-dummy-key")
