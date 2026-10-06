# Which pattern should I use?

There are seventeen [patterns](../../examples/README.md). Most projects need one or two. This page helps you pick, and says what each one costs you in complexity.

**Start with the simplest thing that could work**: a [single agent](../../examples/single/) with a good prompt and a typed output. Add a pattern when a test or a real run shows you need it, not before.

## What are you trying to do?

| You need to... | Use | Why |
|---|---|---|
| Start from nothing | [`blank`](../../examples/blank/) | One output type, one prompt, no tools |
| Do one job with one prompt | [`single`](../../examples/single/) | The baseline; nothing to coordinate |
| Let the agent look things up or act on your systems | [`tool_calling`](../../examples/tool_calling/) | Tools, with an error convention the model can recover from |
| Use tools that already exist as an MCP server | [`mcp_tools`](../../examples/mcp_tools/) | Discovered at run time, called over the network |
| Pull structured data out of free text | [`extraction`](../../examples/extraction/) | A validated schema, with retries when the model gets it wrong |
| Answer from your own documents, and show sources | [`rag`](../../examples/rag/) | Search by meaning, and citations the model cannot invent |
| Get exact answers that need many lookups and arithmetic | [`code_mode`](../../examples/code_mode/) | The model writes code that calls your tools, in a sandbox |
| Keep a conversation going | [`conversation`](../../examples/conversation/) | Memory across turns, a bounded context window, streaming |
| Stop and ask a person before a risky action | [`human_in_the_loop`](../../examples/human_in_the_loop/) | A tool call that pauses for approval, then resumes |
| Refuse bad input and unsafe output | [`guardrails`](../../examples/guardrails/) | Checks in code and with a guard model, and safe fallbacks |
| Make a long run survive failures and crashes | [`temporal`](../../examples/temporal/) | A durable workflow: failing tools are retried, a dead worker is replaced |
| Split work across several agents | see below | Six shapes, and the choice matters |

## Several agents: which shape?

Six patterns use more than one agent. They differ in **who decides what happens next**, and that decides how predictable, how fast and how checkable the result is.

| Pattern | Who decides the steps | The steps are... | Reach for it when |
|---|---|---|---|
| [`pipeline`](../../examples/pipeline/) | Your code | always the same, in order | The task is a fixed sequence, and you want a check between steps |
| [`router`](../../examples/router/) | Your code, from a cheap classification | one specialist, chosen per input | Different kinds of input need different handling |
| [`fan_out`](../../examples/fan_out/) | Your code | the same job, in parallel, then combined | Independent views or chunks, and time matters |
| [`evaluator_optimizer`](../../examples/evaluator_optimizer/) | A critic, in a loop | repeated until the criteria are met, up to a cap | A first draft is usually close and you can state what "good" means |
| [`supervisor`](../../examples/supervisor/) | The model, one turn at a time | whichever workers it chooses to call | You cannot know the steps in advance |
| [`planner_executor`](../../examples/planner_executor/) | The model, once, up front; code checks it | a plan with dependencies, run in rounds | The work varies by question, parts are independent, and you want the plan checked or shown before it runs |

A rough order, from most predictable to most flexible: `pipeline`, `router`, `fan_out`, `evaluator_optimizer`, `planner_executor`, `supervisor`. Predictable is cheaper to test, to debug and to explain. Choose the first one on that list that fits, and move down only when the task forces you to.

- If you can write the steps as a list today, use `pipeline`.
- If the input decides which handler runs, use `router`.
- If the pieces do not depend on each other, use `fan_out`.
- If quality is the problem and you can describe it, use `evaluator_optimizer`.
- If the steps depend on the question, but you want them checked before anything runs, use `planner_executor`.
- If you cannot know the steps until you are partway through, use `supervisor`.

## Where is the risk?

| Your concern | Use |
|---|---|
| The model might do something irreversible | [`human_in_the_loop`](../../examples/human_in_the_loop/) |
| Input might contain data you must not send to a model | [`guardrails`](../../examples/guardrails/) |
| The model might state something it cannot support | [`rag`](../../examples/rag/) (citations are checked against what was retrieved) |
| The model might get arithmetic wrong | [`code_mode`](../../examples/code_mode/) |
| A run might die halfway | [`temporal`](../../examples/temporal/) |

## What does it need?

Most patterns need nothing beyond the template. These need more, and `add_agent.py` handles it:

| Pattern | Extra package | A service |
|---|---|---|
| [`rag`](../../examples/rag/) | `chromadb-client` | Chroma (Docker) |
| [`temporal`](../../examples/temporal/) | `temporalio` | Temporal (Docker) |
| [`mcp_tools`](../../examples/mcp_tools/) | none | an MCP server (Docker) |
| [`code_mode`](../../examples/code_mode/) | `pydantic-ai-harness[code-mode]` | none |

## Combining patterns

Every pattern is a single `run_*` function returning the same [`RunResult`](../../README.md#agents), so patterns compose in ordinary Python: you can call one from another, or run a guardrail before any of them. The examples each show one pattern and do not ship combinations, so a combination is yours to test. Copy each pattern you want with `add_agent.py`, and write the glue in a module of your own.

## Not sure?

Run the [`single`](../../examples/single/) example on your real input and look at where it falls short. The shortfall usually names the pattern: wrong facts point to `rag` or a tool, bad structure to `extraction`, a task that is really three tasks to `pipeline` or `planner_executor`.
