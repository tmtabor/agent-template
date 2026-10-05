"""Code mode: let the model write code that calls your tools, in a sandbox.

Use this pattern when:
- A question needs many tool calls (loop over records, join two lookups, aggregate)
- It needs exact arithmetic, which models get wrong when they add numbers in their head
- You want one or two model round trips instead of dozens

How it works: the `CodeMode` capability (from `pydantic-ai-harness`) hides the agent's tools behind a
single `run_code` tool. The model writes Python that calls them as `await get_expense(expense_id=...)`;
the code runs in **Monty**, a minimal Python interpreter built to run untrusted code. Each call the code
makes really runs your tool on the host, with your deps. Compare "how much did Maya spend on travel":

    plain tool calling   list ids → get_expense × 10 → get_exchange_rate × 3, then add them up by hand
    code mode            one `run_code` call: a loop that fetches, converts and sums, exactly

The sandbox has no filesystem, environment, clock, network or subprocess, and it is bounded: a time
limit, a memory limit, and a cap on how many tool calls one snippet may make. The code is also
type-checked against your tools' signatures before it runs, so a wrong argument is caught first. A
snippet that breaks a rule fails with an error the model reads and can fix; nothing happens on the
host. Those limits are set below (`SANDBOX_LIMITS`, `MAX_TOOL_CALLS`).

The expense data is invented and held in memory so the example runs anywhere. Replace the tools with
your own (an API, a database); `deps.calls` is a ledger of every tool call that really ran.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext, ToolFailed
from pydantic_ai.capabilities import RaiseContentFilterError
from pydantic_ai.usage import UsageLimits
from pydantic_ai_harness import CodeMode

from agent.config import settings
from agent.logging import agent_label, configure_logging, get_logger
from agent.prompts.templates import load_prompt
from agent.runs import Flow, RunResult

logger = get_logger(__name__)
LABEL = agent_label(__name__)  # names this agent's run spans in Logfire traces

# The model's requests, not the sandbox's tool calls: code mode needs few of them, so this is tight.
USAGE_LIMITS = UsageLimits(
    request_limit=8, total_tokens_limit=100_000, cost_limit=settings.cost_limit
)

# --- The sandbox's limits ---
MAX_TOOL_CALLS = 60  # tool calls one `run_code` snippet may make (a runaway loop stops here)
SANDBOX_LIMITS = {
    "max_duration_secs": 2.0,  # CPU time per snippet; time spent waiting on tools does not count
    "max_memory": 100_000_000,  # bytes
}


# --- The data ---
@dataclass(frozen=True)
class Employee:
    id: str
    name: str


Category = Literal["travel", "meals", "lodging", "supplies"]


@dataclass(frozen=True)
class Expense:
    id: str
    employee_id: str
    category: Category  # spelled out, so the model's code sees the exact values to compare against
    amount: float
    currency: str  # a three-letter code such as "EUR"


EMPLOYEES: tuple[Employee, ...] = (
    Employee("E1", "Arjun"),
    Employee("E2", "Maya"),
    Employee("E3", "Tomas"),
)

# Replace with a real data source. Mixed currencies on purpose: the arithmetic is what code is for.
EXPENSES: tuple[Expense, ...] = (
    Expense("X101", "E1", "travel", 412.50, "USD"),
    Expense("X102", "E1", "meals", 38.20, "EUR"),
    Expense("X103", "E1", "travel", 129.00, "GBP"),
    Expense("X104", "E1", "meals", 22.75, "USD"),
    Expense("X105", "E1", "lodging", 640.00, "USD"),
    Expense("X106", "E1", "meals", 5400.00, "JPY"),
    Expense("X107", "E1", "supplies", 88.10, "CAD"),
    Expense("X108", "E1", "travel", 61.40, "EUR"),
    Expense("X201", "E2", "travel", 950.00, "EUR"),
    Expense("X202", "E2", "meals", 41.60, "USD"),
    Expense("X203", "E2", "travel", 18200.00, "JPY"),
    Expense("X204", "E2", "lodging", 420.00, "GBP"),
    Expense("X205", "E2", "travel", 75.25, "USD"),
    Expense("X206", "E2", "meals", 64.30, "CAD"),
    Expense("X207", "E2", "supplies", 29.99, "USD"),
    Expense("X208", "E2", "travel", 233.80, "GBP"),
    Expense("X209", "E2", "meals", 17.40, "EUR"),
    Expense("X301", "E3", "meals", 120.00, "USD"),
    Expense("X302", "E3", "travel", 305.40, "CAD"),
    Expense("X303", "E3", "meals", 87.50, "GBP"),
    Expense("X304", "E3", "lodging", 510.00, "EUR"),
    Expense("X305", "E3", "meals", 9800.00, "JPY"),
    Expense("X306", "E3", "supplies", 14.20, "USD"),
)

# How many US dollars one unit of each currency is worth.
RATES_TO_USD: dict[str, float] = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "JPY": 0.0067, "CAD": 0.74}


# --- Dependencies ---
@dataclass
class ExpenseDeps:
    """Runtime dependencies for the expenses agent."""

    employees: tuple[Employee, ...] = EMPLOYEES
    expenses: tuple[Expense, ...] = EXPENSES
    rates: dict[str, float] = field(default_factory=lambda: dict(RATES_TO_USD))
    # Every tool call that really ran on the host, in order: ("get_expense", "X101"). The sandbox is
    # a boundary, so this is the ground truth for what the model's code actually did.
    calls: list[tuple[str, str]] = field(default_factory=list)


# --- Output type ---
class Answer(BaseModel):
    # `result` is the conventional output field in these examples; the generated
    # eval starter reads it when present (see evals/helpers.py).
    result: str
    amount_usd: float  # the dollar figure the question asked for
    subject: str  # the employee id or expense id the answer is about


# --- Agent ---
code_mode_agent: Agent[ExpenseDeps, Answer] = Agent(
    settings.model,
    name=LABEL,
    output_type=Answer,
    deps_type=ExpenseDeps,
    capabilities=[
        RaiseContentFilterError(),
        # Every tool below becomes a function the model's code can call; `run_code` is the only tool the
        # model sees. Pass `tools=[...]` to leave some as ordinary tool calls instead.
        CodeMode(max_tool_calls=MAX_TOOL_CALLS, resource_limits=SANDBOX_LIMITS),
    ],
    instructions=load_prompt("code_mode"),  # prompts/…; copied to agent/prompts/<name>.txt
)


# --- Tools: ordinary tools. Code mode makes them callable from the sandbox. ---
@code_mode_agent.tool
async def list_employees(ctx: RunContext[ExpenseDeps]) -> list[Employee]:
    """Every employee: their id and name."""
    ctx.deps.calls.append(("list_employees", ""))
    return list(ctx.deps.employees)


@code_mode_agent.tool
async def list_expense_ids(ctx: RunContext[ExpenseDeps], employee_id: str) -> list[str]:
    """The ids of one employee's expenses.

    Args:
        employee_id: The employee's id, such as "E2".

    Raises:
        ToolFailed: When there is no such employee.
    """
    ctx.deps.calls.append(("list_expense_ids", employee_id))
    if not any(e.id == employee_id for e in ctx.deps.employees):
        raise ToolFailed(f"There is no employee {employee_id!r}.")
    return [x.id for x in ctx.deps.expenses if x.employee_id == employee_id]


@code_mode_agent.tool
async def get_expense(ctx: RunContext[ExpenseDeps], expense_id: str) -> Expense:
    """One expense: its category, amount and currency.

    Args:
        expense_id: The expense id, such as "X101".

    Raises:
        ToolFailed: When there is no such expense.
    """
    ctx.deps.calls.append(("get_expense", expense_id))
    for expense in ctx.deps.expenses:
        if expense.id == expense_id:
            return expense
    raise ToolFailed(f"There is no expense {expense_id!r}.")


@code_mode_agent.tool
async def get_exchange_rate(ctx: RunContext[ExpenseDeps], currency: str) -> float:
    """How many US dollars one unit of `currency` is worth (multiply an amount by it).

    Args:
        currency: A three-letter code such as "EUR".

    Raises:
        ToolFailed: When the currency is not supported.
    """
    ctx.deps.calls.append(("get_exchange_rate", currency))
    try:
        return ctx.deps.rates[currency]
    except KeyError:
        raise ToolFailed(
            f"No rate for {currency!r}. Supported: {', '.join(sorted(ctx.deps.rates))}."
        ) from None


# --- Grounding ---
@code_mode_agent.output_validator
def check_the_subject_exists(ctx: RunContext[ExpenseDeps], answer: Answer) -> Answer:
    """The answer must point at a real employee or expense, so a made-up id is sent back."""
    known = {e.id for e in ctx.deps.employees} | {x.id for x in ctx.deps.expenses}
    if answer.subject not in known:
        raise ModelRetry(
            f"`subject` {answer.subject!r} is not an employee or expense id. Use an id from the data, "
            "such as an employee id like 'E2' or an expense id like 'X101'."
        )
    return answer


async def run_expenses(user_input: str, deps: ExpenseDeps | None = None) -> RunResult[Answer]:
    """Answer a question about the expense reports, using code to call the tools.

    Returns:
        A RunResult: `.output` is the `Answer`. The model's code is in `.all_messages()` (the
        `run_code` calls), and `deps.calls` records every tool call the code made.
    """
    if deps is None:
        deps = ExpenseDeps()
    logger.info("Running expenses agent", extra={"user_input": user_input})
    flow = Flow(USAGE_LIMITS)
    result = await flow.run(code_mode_agent, user_input, deps=deps)
    return flow.finish(result.output)


if __name__ == "__main__":
    import asyncio

    configure_logging()
    deps = ExpenseDeps()
    result = asyncio.run(
        run_expenses("What is the total of Maya's travel expenses, in US dollars?", deps)
    )
    print(
        result.output, f"| {len(deps.calls)} tool calls in {result.usage.requests} model requests"
    )
