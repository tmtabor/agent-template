"""cost_limit is optional and off by default (AGENT_COST_LIMIT).

When it is unset, no cost limit is passed to UsageLimits, so Pydantic AI never
emits a CostNotFoundWarning — which it does on every run for models it can't
price (e.g. ollama:) if a limit is set. When it is set, it is enforced.
"""

import dataclasses
import warnings
from decimal import Decimal

import pytest
from pydantic_ai._warnings import CostNotFoundWarning
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from agent.config import Settings, settings
from tests.examples_support import example_ids, import_example


def test_cost_limit_is_off_by_default():
    assert Settings.model_fields["cost_limit"].default is None


def test_cost_limit_setting_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("AGENT_COST_LIMIT", "0.25")
    assert Settings().cost_limit == Decimal("0.25")


@pytest.mark.parametrize("example", example_ids())
def test_example_limits_follow_the_setting(example):
    module = import_example(example)
    assert module.USAGE_LIMITS.cost_limit == settings.cost_limit


@pytest.mark.parametrize("example", example_ids())
async def test_no_cost_warning_when_no_cost_limit_is_set(example):
    module = import_example(example)
    if settings.cost_limit is not None:
        pytest.skip("AGENT_COST_LIMIT is set in this environment")

    main_agent = getattr(module, example.agent)
    deps = getattr(module, example.deps)()
    model = TestModel(call_tools=list(example.smoke_tools))
    with main_agent.override(model=model), warnings.catch_warnings():
        warnings.simplefilter("error", CostNotFoundWarning)
        await main_agent.run("Smoke test input", deps=deps, usage_limits=module.USAGE_LIMITS)


@pytest.mark.parametrize("example", example_ids())
async def test_cost_limit_is_enforced_when_set(example):
    module = import_example(example)
    limits = dataclasses.replace(module.USAGE_LIMITS, cost_limit=Decimal("0.50"))

    # TestModel can't be priced, so seed a usage already over the cap.
    main_agent = getattr(module, example.agent)
    deps = getattr(module, example.deps)()
    with pytest.raises(UsageLimitExceeded, match="cost_limit"):
        await main_agent.run(
            "Smoke test input",
            deps=deps,
            usage=RunUsage(cost=Decimal("1")),
            usage_limits=limits,
        )
