"""The tools, the answer check, and — the point of the example — what the sandbox lets code do.

Monty is real and local, so these run actual model-style code in the actual sandbox with a scripted
model, and check what happened on the *host* (the tool-call ledger, files, time). Needs
pydantic-ai-harness (declared in example.toml), so it is skipped without it and run in the example's own
environment by scripts/release_check.py.
"""

import time
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai_harness", reason="needs pydantic-ai-harness[code-mode]")

from pydantic_ai import ModelRetry, RunContext, ToolFailed  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402
from pydantic_ai.usage import RunUsage  # noqa: E402

from examples.code_mode.agent import (  # noqa: E402
    EMPLOYEES,
    EXPENSES,
    MAX_TOOL_CALLS,
    RATES_TO_USD,
    SANDBOX_LIMITS,
    Answer,
    ExpenseDeps,
    check_the_subject_exists,
    code_mode_agent,
    get_exchange_rate,
    get_expense,
    list_employees,
    list_expense_ids,
    run_expenses,
)


def ctx(deps: ExpenseDeps | None = None) -> RunContext[ExpenseDeps]:
    return RunContext(deps=deps or ExpenseDeps(), model=TestModel(), usage=RunUsage())


def truth(employee_id: str, category: str) -> float:
    """The right answer, worked out independently of the model and of the sandbox."""
    return round(
        sum(
            x.amount * RATES_TO_USD[x.currency]
            for x in EXPENSES
            if x.employee_id == employee_id and x.category == category
        ),
        2,
    )


# --- The data ---


def test_the_data_is_consistent_so_the_ground_truth_can_be_trusted():
    assert len({x.id for x in EXPENSES}) == len(EXPENSES)  # ids are unique
    assert {x.employee_id for x in EXPENSES} <= {e.id for e in EMPLOYEES}
    assert {x.currency for x in EXPENSES} <= set(RATES_TO_USD)
    assert truth("E2", "travel") == 1520.12 and max(
        (truth(e.id, "meals"), e.id) for e in EMPLOYEES
    ) == (296.78, "E3")


# --- The tools, called directly; each records itself in the ledger ---


async def test_employees_are_listed_and_recorded():
    deps = ExpenseDeps()
    assert [e.name for e in await list_employees(ctx(deps))] == ["Arjun", "Maya", "Tomas"]
    assert deps.calls == [("list_employees", "")]


async def test_an_employees_expense_ids_are_listed():
    deps = ExpenseDeps()
    ids = await list_expense_ids(ctx(deps), "E2")
    assert ids == [x.id for x in EXPENSES if x.employee_id == "E2"] and len(ids) == 9
    assert deps.calls == [("list_expense_ids", "E2")]


async def test_an_unknown_employee_is_a_terminal_failure():
    with pytest.raises(ToolFailed, match="no employee 'E9'"):
        await list_expense_ids(ctx(), "E9")


async def test_one_expense_is_returned_whole():
    expense = await get_expense(ctx(), "X201")
    assert (expense.employee_id, expense.category, expense.amount, expense.currency) == (
        "E2",
        "travel",
        950.0,
        "EUR",
    )


async def test_an_unknown_expense_is_a_terminal_failure():
    with pytest.raises(ToolFailed, match="no expense 'X999'"):
        await get_expense(ctx(), "X999")


async def test_a_rate_is_looked_up_and_an_unknown_currency_lists_the_supported_ones():
    assert await get_exchange_rate(ctx(), "EUR") == 1.08
    with pytest.raises(ToolFailed, match="Supported: CAD, EUR, GBP, JPY, USD"):
        await get_exchange_rate(ctx(), "XYZ")


def test_each_run_gets_its_own_ledger():
    assert ExpenseDeps().calls is not ExpenseDeps().calls


# --- The answer check ---


@pytest.mark.parametrize("subject", ["E2", "X101"])
def test_an_employee_or_expense_id_is_accepted(subject):
    answer = Answer(result="r", amount_usd=1.0, subject=subject)
    assert check_the_subject_exists(ctx(), answer) is answer


def test_an_id_that_does_not_exist_is_sent_back():
    with pytest.raises(ModelRetry, match="'Maya' is not an employee or expense id"):
        check_the_subject_exists(ctx(), Answer(result="r", amount_usd=1.0, subject="Maya"))


# --- A scripted model that writes code ---


def scripted(*steps: dict, seen: list | None = None):
    """Follow `steps`: {"code": ...} calls `run_code`; {"output": {...}} gives the final answer."""
    remaining = list(steps)

    def model_fn(messages, info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append((messages, info))
        step = remaining.pop(0)
        if "code" in step:
            return ModelResponse(parts=[ToolCallPart("run_code", {"code": step["code"]})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, step["output"])])

    return FunctionModel(model_fn)


def done(amount: float = 0.0, subject: str = "E2") -> dict:
    return {"output": {"result": "done", "amount_usd": amount, "subject": subject}}


def run_code_results(result) -> list[str]:
    return [
        str(part.content)
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "run_code"
    ]


def retry_messages(result) -> list[str]:
    return [
        str(part.content)
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]


MAYA_TRAVEL = """
employees = await list_employees()
maya = ''
for e in employees:
    if e['name'] == 'Maya':
        maya = e['id']
total = 0.0
rates = {}
for expense_id in await list_expense_ids(employee_id=maya):
    expense = await get_expense(expense_id=expense_id)
    if expense['category'] == 'travel':
        if expense['currency'] not in rates:
            rates[expense['currency']] = await get_exchange_rate(currency=expense['currency'])
        total += expense['amount'] * rates[expense['currency']]
round(total, 2)
"""


async def test_the_model_sees_one_tool_and_it_is_run_code():
    seen: list = []
    with code_mode_agent.override(model=scripted(done(), seen=seen)):
        await run_expenses("anything")
    tools = seen[0][1].function_tools
    assert [t.name for t in tools] == ["run_code"]  # the five real tools are not offered directly
    description = tools[0].description or ""
    for name in ("list_employees", "list_expense_ids", "get_expense", "get_exchange_rate"):
        assert name in description  # …but the model is told it can call them from its code


async def test_one_snippet_does_the_work_of_dozens_of_tool_calls_and_gets_the_exact_answer():
    deps = ExpenseDeps()
    with code_mode_agent.override(model=scripted({"code": MAYA_TRAVEL}, done(1520.12))):
        result = await run_expenses("Maya's travel total?", deps)

    assert run_code_results(result) == ["1520.12"] and float(run_code_results(result)[0]) == truth(
        "E2", "travel"
    )
    assert result.usage.requests == 2  # the snippet, then the answer
    # The ledger is what really ran on the host: all nine of Maya's expenses, fetched by the code.
    fetched = [arg for name, arg in deps.calls if name == "get_expense"]
    assert fetched == [x.id for x in EXPENSES if x.employee_id == "E2"]
    assert len(deps.calls) >= 12  # many tool calls from a single model request
    assert result.output.amount_usd == 1520.12


async def test_independent_lookups_can_run_concurrently_from_one_snippet():
    code = """
import asyncio
rates = await asyncio.gather(*[get_exchange_rate(currency=c) for c in ['EUR', 'GBP', 'JPY']])
rates
"""
    deps = ExpenseDeps()
    with code_mode_agent.override(model=scripted({"code": code}, done())):
        result = await run_expenses("rates", deps)
    assert run_code_results(result) == ["[1.08, 1.27, 0.0067]"]
    assert sorted(arg for _, arg in deps.calls) == ["EUR", "GBP", "JPY"]


async def test_state_survives_between_snippets_like_a_repl():
    steps = [{"code": "n = len(await list_employees())"}, {"code": "n * 10"}, done()]
    with code_mode_agent.override(model=scripted(*steps)):
        result = await run_expenses("state")
    assert run_code_results(result)[-1] == "30"


async def test_a_tool_that_fails_inside_the_code_tells_the_model_why():
    code = "await get_expense(expense_id='X999')"
    with code_mode_agent.override(model=scripted({"code": code}, done())):
        result = await run_expenses("missing")
    assert any("no expense 'X999'" in m for m in retry_messages(result))


async def test_the_model_recovers_from_a_mistake_in_its_own_code():
    steps = [
        {"code": "expense = await get_expense(expense_id='X101')\nexpense['amount_in_dollars']"},
        {"code": "expense = await get_expense(expense_id='X101')\nexpense['amount']"},
        done(412.5, "X101"),
    ]
    deps = ExpenseDeps()
    with code_mode_agent.override(model=scripted(*steps)):
        result = await run_expenses("one expense", deps)

    assert len(retry_messages(result)) == 1 and "amount_in_dollars" in retry_messages(result)[0]
    assert run_code_results(result) == ["412.5"] and result.output.subject == "X101"


# --- What the sandbox does not allow: each hostile snippet is refused, and the host is untouched ---


async def hostile(code: str, deps: ExpenseDeps | None = None):
    """Run one snippet of untrusted code; the model then recovers and answers."""
    deps = deps or ExpenseDeps()
    with code_mode_agent.override(model=scripted({"code": code}, done())):
        result = await run_expenses("do something unsafe", deps)
    return result, deps


async def test_code_cannot_read_a_file_on_the_host():
    result, deps = await hostile("open('/etc/passwd').read()")
    # Refused before it runs: the sandbox has no `open` at all (the exact wording is Monty's).
    assert retry_messages(result) and not run_code_results(result)
    assert "root:" not in " ".join(retry_messages(result))  # and nothing from the file came back
    assert deps.calls == []


async def test_pathlib_can_be_imported_but_cannot_touch_the_filesystem():
    result, _ = await hostile("from pathlib import Path\nPath('/etc/passwd').read_text()")
    assert any("PermissionError" in m for m in retry_messages(result))
    assert not run_code_results(result)


async def test_code_cannot_write_a_file_on_the_host(tmp_path: Path):
    target = tmp_path / "pwned.txt"
    result, _ = await hostile(f"open({str(target)!r}, 'w').write('x')")
    assert retry_messages(result) and not run_code_results(result)
    assert not target.exists()  # the file was never created on the real filesystem


async def test_pathlib_cannot_write_a_file_either(tmp_path: Path):
    target = tmp_path / "pwned.txt"
    result, _ = await hostile(f"from pathlib import Path\nPath({str(target)!r}).write_text('x')")
    assert any("PermissionError" in m for m in retry_messages(result))
    assert not target.exists()


async def test_code_cannot_list_a_directory():
    result, _ = await hostile("import os\nos.listdir('/')")
    assert any("PermissionError" in m for m in retry_messages(result))


async def test_code_cannot_read_environment_variables(monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "hunter2")
    result, _ = await hostile("import os\nos.environ['SECRET_TOKEN']")
    assert retry_messages(result)
    assert "hunter2" not in " ".join(retry_messages(result) + run_code_results(result))


async def test_code_cannot_read_the_clock():
    result, _ = await hostile("import time\ntime.time()")
    assert any("not supported in this environment" in m for m in retry_messages(result))


@pytest.mark.parametrize("module", ["socket", "subprocess"])
async def test_code_cannot_reach_the_network_or_start_a_process(module):
    result, _ = await hostile(f"import {module}\n{module}")
    assert any(f"Cannot resolve imported module `{module}`" in m for m in retry_messages(result))


async def test_a_runaway_loop_is_stopped_at_the_time_limit():
    started = time.perf_counter()
    result, _ = await hostile("while True:\n    pass")
    elapsed = time.perf_counter() - started
    assert any("max_duration_secs" in m for m in retry_messages(result))
    assert SANDBOX_LIMITS["max_duration_secs"] <= elapsed < SANDBOX_LIMITS["max_duration_secs"] + 3


async def test_a_memory_bomb_is_refused():
    result, _ = await hostile("blob = 'x' * (10**10)\nlen(blob)")
    assert any("MemoryError" in m for m in retry_messages(result))


async def test_a_runaway_tool_loop_is_capped_and_only_that_many_calls_reach_the_host():
    code = "for i in range(1000):\n    await get_exchange_rate(currency='EUR')"
    result, deps = await hostile(code)
    assert any(f"allows {MAX_TOOL_CALLS} nested tool calls" in m for m in retry_messages(result))
    assert len(deps.calls) == MAX_TOOL_CALLS  # exactly the cap, not 1000


async def test_a_refused_snippet_does_not_end_the_run_the_model_can_carry_on():
    result, _ = await hostile("open('/etc/passwd')")
    assert result.output.result == "done"  # it recovered and answered


# --- The configuration itself ---


def test_the_sandbox_limits_are_finite_and_set():
    assert 0 < SANDBOX_LIMITS["max_duration_secs"] <= 10
    assert 0 < SANDBOX_LIMITS["max_memory"] <= 1_000_000_000
    assert 0 < MAX_TOOL_CALLS <= 200
