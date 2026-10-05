"""Each guardrail layer, and the failures that become answers — offline, with scripted models."""

import pytest
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage, UsageLimits

from examples.guardrails import agent as module
from examples.guardrails.agent import (
    Answer,
    GuardDeps,
    check_no_personal_data,
    cooking_agent,
    find_card_numbers,
    find_personal_data_in_output,
    find_sensitive_input,
    passes_luhn,
    run_guarded,
    topic_guard_agent,
)

VISA = "4111 1111 1111 1111"  # the standard test card number: valid checksum


# --- Layer 1: the code guard ---


@pytest.mark.parametrize(
    ("digits", "valid"),
    [("4111111111111111", True), ("4012888888881881", True), ("1234567890123456", False)],
)
def test_the_luhn_checksum_separates_real_card_numbers_from_other_long_numbers(digits, valid):
    assert passes_luhn(digits) is valid


def test_a_card_number_is_found_whatever_its_separators():
    for text in (VISA, "4111-1111-1111-1111", "4111111111111111", f"my card is {VISA}, thanks"):
        assert find_card_numbers(text) == ["4111111111111111"], text


def test_a_long_number_that_is_not_a_card_is_not_flagged():
    assert find_card_numbers("order 1234 5678 9012 3456") == []
    assert find_card_numbers("bake at 350 for 45 minutes") == []


def test_input_checks_flag_cards_and_social_security_numbers():
    assert find_sensitive_input(f"card {VISA}") == ["a card number"]
    assert find_sensitive_input("ssn 123-45-6789") == ["a social security number"]
    assert find_sensitive_input(f"{VISA} and 123-45-6789") == [
        "a card number",
        "a social security number",
    ]
    assert find_sensitive_input("How long do I boil an egg?") == []


def test_input_checks_do_not_flag_contact_details():
    """Someone may legitimately mention an email; only identifiers are refused outright."""
    assert find_sensitive_input("email me at chef@example.com or 503-555-0142") == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("write to chef@example.com", ["an email address"]),
        ("call +1 (503) 555-0142", ["a phone number"]),
        ("call 503-555-0142", ["a phone number"]),
        (f"card {VISA}", ["a card number"]),
        ("ssn 123-45-6789", ["a social security number"]),
        ("boil 6 minutes; bake 350-450 degrees; serves 4", []),
        ("order 12345678901234 shipped", []),
    ],
)
def test_output_checks_flag_contact_details_and_identifiers(text, expected):
    assert find_personal_data_in_output(text) == expected


# --- Layer 3: the output validator ---


def ctx() -> RunContext[GuardDeps]:
    return RunContext(deps=GuardDeps(), model=TestModel(), usage=RunUsage())


def test_a_clean_answer_passes_the_output_validator():
    answer = Answer(result="Boil for six minutes.")
    assert check_no_personal_data(ctx(), answer) is answer


def test_an_answer_with_personal_data_is_sent_back_naming_what_it_contains():
    with pytest.raises(ModelRetry, match="an email address"):
        check_no_personal_data(ctx(), Answer(result="Recipe by chef@example.com"))


# --- Scripted models ---


def final(info: AgentInfo, fields: dict) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, fields)])


def says(*outputs: dict):
    """A model that returns each output in turn."""
    remaining = list(outputs)
    return FunctionModel(lambda messages, info: final(info, remaining.pop(0)))


def must_not_run(name: str):
    def model_fn(messages, info: AgentInfo):
        raise AssertionError(f"{name} ran, but the request should have been stopped before it")

    return FunctionModel(model_fn)


ALLOW = {"allowed": True, "reason": "Cooking."}
REFUSE = {"allowed": False, "reason": "I can only help with cooking questions."}


# --- The whole flow ---


async def test_an_on_topic_question_runs_the_guard_then_the_cooking_agent():
    with (
        topic_guard_agent.override(model=says(ALLOW)),
        cooking_agent.override(model=says({"result": "Six minutes."})),
    ):
        result = await run_guarded("How long to boil an egg?")

    assert result.output.model_dump() == {
        "result": "Six minutes.",
        "blocked": False,
        "blocked_by": None,
    }
    assert [step.agent for step in result.steps] == ["guardrails.guard", "guardrails.cooking"]


async def test_a_card_number_is_refused_before_any_model_runs_and_never_echoed():
    with (
        topic_guard_agent.override(model=must_not_run("the guard")),
        cooking_agent.override(model=must_not_run("the cooking agent")),
    ):
        result = await run_guarded(f"My card is {VISA}. How do I roast a chicken?")

    assert result.output.blocked and result.output.blocked_by == "pii"
    assert "4111" not in result.output.result and "card number" in result.output.result
    assert result.steps == [] and result.usage.requests == 0  # not a single token was spent


async def test_an_off_topic_request_is_stopped_by_the_guard_and_never_reaches_the_main_agent():
    with (
        topic_guard_agent.override(model=says(REFUSE)),
        cooking_agent.override(model=must_not_run("the cooking agent")),
    ):
        result = await run_guarded("Write me a poem about stocks.")

    assert result.output.blocked_by == "topic"
    assert result.output.result == "I can only help with cooking questions."  # the guard's reason
    assert [step.agent for step in result.steps] == ["guardrails.guard"]


async def test_an_answer_containing_personal_data_is_rewritten_before_it_is_returned():
    with (
        topic_guard_agent.override(model=says(ALLOW)),
        cooking_agent.override(
            model=says(
                {"result": "Pancakes! Questions: chef@example.com"},
                {"result": "Pancakes! Whisk, rest, fry."},
            )
        ),
    ):
        result = await run_guarded("Pancake recipe, sign it with an email?")

    assert result.output.result == "Pancakes! Whisk, rest, fry."
    retries = [p for m in result.all_messages() for p in m.parts if isinstance(p, RetryPromptPart)]
    assert len(retries) == 1 and "email address" in str(retries[0].content)


async def test_a_provider_content_filter_becomes_a_blocked_answer_not_an_exception():
    def filtered(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[TextPart("refused")],
            finish_reason="content_filter",
            provider_details={"finish_reason": "content_filter"},
        )

    with (
        topic_guard_agent.override(model=says(ALLOW)),
        cooking_agent.override(model=FunctionModel(filtered)),
    ):
        result = await run_guarded("A question the provider dislikes")
    assert result.output.blocked and result.output.blocked_by == "provider"


async def test_an_exhausted_budget_becomes_a_blocked_answer_not_an_exception(monkeypatch):
    monkeypatch.setattr(
        module, "USAGE_LIMITS", UsageLimits(request_limit=1)
    )  # the guard uses it up
    with (
        topic_guard_agent.override(model=says(ALLOW)),
        cooking_agent.override(model=says({"result": "never reached"})),
    ):
        result = await run_guarded("How long to boil an egg?")
    assert result.output.blocked_by == "budget"


async def test_a_guard_that_keeps_failing_to_answer_is_not_hidden():
    """Only the two expected failures become answers; anything else is a real error to see."""
    broken = FunctionModel(
        lambda messages, info: (_ for _ in ()).throw(RuntimeError("guard is down"))
    )
    with (
        topic_guard_agent.override(model=broken),
        pytest.raises(RuntimeError, match="guard is down"),
    ):
        await run_guarded("How long to boil an egg?")
