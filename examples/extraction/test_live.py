"""Live check: the model fills the schema, and bad input exhausts the retries. `pytest -m eval`."""

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from evals.trace import traced_run
from examples.extraction import agent as module
from examples.live_support import assert_every_agent_ran, run_as_script

pytestmark = pytest.mark.eval


def has_digits(value: str | None) -> bool:
    """Whether a field holds a number. Models sometimes write the string "None" for an empty
    field instead of null; that is a harmless quirk, while an invented number is the failure."""
    return value is not None and any(ch.isdigit() for ch in value)


@pytest.fixture(scope="module")
async def with_email():
    return await traced_run(
        module.run_extraction,
        "Hi, it's Ada Lovelace from Analytical Engines Ltd. Reach me at ada@example.com.",
    )


@pytest.fixture(scope="module")
async def phone_only():
    return await traced_run(module.run_extraction, "Reach Grace Hopper at +1 555 0100.")


async def test_a_contact_with_an_email_is_extracted_exactly(with_email):
    contact = with_email.result.output
    assert contact.name == "Ada Lovelace"
    assert contact.email == "ada@example.com"
    # The text reads "Analytical Engines Ltd. Reach me…", so a trailing period is faithful.
    assert contact.company is not None and contact.company.startswith("Analytical Engines Ltd")
    assert not has_digits(contact.phone)  # not in the text, so not invented


async def test_a_phone_only_contact_is_accepted_without_an_email(phone_only):
    contact = phone_only.result.output
    assert contact.name == "Grace Hopper"
    assert contact.email is None or "@" not in contact.email  # no address in the text
    assert contact.phone is not None and "555 0100" in contact.phone


async def test_text_with_no_way_to_reach_anyone_exhausts_the_retries_instead_of_inventing_one():
    """The validator rejects a contact with neither email nor phone; the model can't comply."""
    with pytest.raises(UnexpectedModelBehavior, match="retries"):
        await module.run_extraction("Lovely weather today, isn't it?")


async def test_each_run_is_one_agent_step(with_email, phone_only):
    for traced in (with_email, phone_only):
        assert [step.agent for step in traced.result.steps] == ["extraction"]
    assert_every_agent_ran(module, with_email.agents_ran | phone_only.agents_ran)


async def test_the_demo_script_runs():
    assert "ada@example.com" in await run_as_script("examples.extraction.agent")
