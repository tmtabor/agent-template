"""cost_limit is optional and off by default (AGENT_COST_LIMIT).

When it is unset, no cost limit is passed to UsageLimits, so Pydantic AI never
emits a CostNotFoundWarning — which it does on every run for models it can't
price (e.g. ollama:) if a limit is set. When it is set, it is enforced.
"""

import dataclasses
import importlib
import warnings
from decimal import Decimal

import pytest
from pydantic_ai._warnings import CostNotFoundWarning
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from agent.config import Settings, settings
from tests.test_stubs import SMOKE_TOOLS, STUBS


def _import_stub(module_path: str):
    try:
        return importlib.import_module(module_path)
    except ModuleNotFoundError:
        pytest.skip(f"{module_path} stub was removed by choose_pattern.py")


def test_cost_limit_is_off_by_default():
    assert Settings.model_fields["cost_limit"].default is None


def test_cost_limit_setting_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("AGENT_COST_LIMIT", "0.25")
    assert Settings().cost_limit == Decimal("0.25")


@pytest.mark.parametrize(("module_path", "agent_attr", "deps_attr"), STUBS)
def test_stub_limits_follow_the_setting(module_path: str, agent_attr: str, deps_attr: str):
    module = _import_stub(module_path)
    assert module.USAGE_LIMITS.cost_limit == settings.cost_limit


@pytest.mark.parametrize(("module_path", "agent_attr", "deps_attr"), STUBS)
async def test_no_cost_warning_when_no_cost_limit_is_set(
    module_path: str, agent_attr: str, deps_attr: str
):
    module = _import_stub(module_path)
    if settings.cost_limit is not None:
        pytest.skip("AGENT_COST_LIMIT is set in this environment")

    main_agent = getattr(module, agent_attr)
    deps = getattr(module, deps_attr)()
    model = TestModel(call_tools=SMOKE_TOOLS.get(module_path, []))
    with main_agent.override(model=model), warnings.catch_warnings():
        warnings.simplefilter("error", CostNotFoundWarning)
        await main_agent.run("Smoke test input", deps=deps, usage_limits=module.USAGE_LIMITS)


@pytest.mark.parametrize(("module_path", "agent_attr", "deps_attr"), STUBS)
async def test_cost_limit_is_enforced_when_set(module_path: str, agent_attr: str, deps_attr: str):
    module = _import_stub(module_path)
    limits = dataclasses.replace(module.USAGE_LIMITS, cost_limit=Decimal("0.50"))

    # TestModel can't be priced, so seed a usage already over the cap.
    main_agent = getattr(module, agent_attr)
    deps = getattr(module, deps_attr)()
    with pytest.raises(UsageLimitExceeded, match="cost_limit"):
        await main_agent.run(
            "Smoke test input",
            deps=deps,
            usage=RunUsage(cost=Decimal("1")),
            usage_limits=limits,
        )
