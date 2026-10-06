# Planner-executor

One agent writes the whole plan; code checks it and carries it out; a last agent writes the answer.

A planner agent writes the whole plan up front as data: a list of steps, each saying what to do and which earlier steps it needs. It never answers and never calls a tool. Code then checks the plan (no repeated ids, no missing dependencies, no cycles, one final step) and sends a bad plan back to the planner to fix. Once the plan is valid, code runs it a round at a time: every step whose dependencies are done runs now, all of those in parallel, and each executor sees only its own step and the results it depends on. A last agent writes the answer from whatever completed. The model chooses the shape once; code holds it to the rules and does the scheduling.

**Use it when**

- A question needs several different pieces of work, and what they are depends on the question.
- Some of the pieces are independent (so they can run at the same time) and some need others' results.
- You want the plan to exist as data you can check, log, show or approve before anything runs.

**Look elsewhere when**

- The steps are always the same: [`pipeline`](../pipeline/) is simpler and cheaper.
- The steps can't be known until you are partway through: [`supervisor`](../supervisor/).
- The pieces never depend on each other: [`fan_out`](../fan_out/).

```
question → planner → Plan(steps) → check in code → executors, a round at a time → synthesizer
                                    (ids, needs,      (independent steps in parallel)
                                     no cycles,
                                     one final step)
```

**What it shows**

- **The model writes the shape once, up front.** The planner never answers and never calls a tool:
  it returns a `Plan` of steps, each with an `id`, an `instruction`, and `depends_on`. Compare
  `supervisor` (the model decides what to delegate one turn at a time) and `pipeline` / `fan_out`
  (the shape is fixed in code)
- **Code holds the plan to rules.** `check_plan` rejects an empty or over-long plan, repeated ids,
  dependencies on steps that don't exist, a step that depends on itself, a cycle, and a plan with
  more than one "final" step. The reason goes back to the planner, which rewrites the plan
  (`retries={"output": 3}`)
- **Rounds, in parallel.** Every step whose dependencies are done runs now, all of those at once
  (`asyncio.gather`). `output.waves` records which steps ran together
- **Each executor sees only what it needs:** its own instruction and the results of the steps it
  depends on, plus the question for context. Not its siblings' results, and not steps upstream that
  it did not name
- **A failure takes down only what needed it.** A step that raises is recorded in `failed`; every
  step that needed it, directly or through others, is `skipped` and never reaches an executor; the
  rest finish. The synthesizer is told which steps failed or were skipped. If nothing completes,
  `AllStepsFailedError`; if the shared budget runs out, `UsageLimitExceeded` ends the run (it is not
  one step's failure)
- **One budget** for the planner, every executor and the synthesizer (`USAGE_LIMITS` on one `Flow`)

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

## What the real model taught us

The model does **not** reliably say which steps a step needs. Asked to plan "look up A, look up B,
then compare", Gemini wrote the comparison with an empty `depends_on` in 9 of 10 sampled plans, even with
the rule spelled out and an example in the prompt. Such a step runs in the same round as the lookups,
without their results, and the answer still came out right only because the executors can look cities
up for themselves and the synthesizer does the arithmetic: the wrong plan was hidden by a right answer.

So the rule lives in code, not in the prompt. A plan must end in **one final step** that every other
step feeds into. Lookups plus a compare step that forgot its dependencies leave several loose ends, and
the check names them and sends the plan back, and the model fixes it (the planner makes two requests
instead of one; 11 of 12 sampled plans needed exactly one correction). The wording of the rejection matters as much as the rule. Saying only what was wrong, the model
repeated the same plan three times and used up its retries; saying what to change ("make 's4' the
final step by setting its depends_on to include ['s1', 's2', 's3']", which the code can work out)
fixed it on the first retry. That is the stronger guarantee, and it has a limit worth knowing: the check
sees the *graph*, not what a step's words need. A calculation step that declares no dependencies but is
used by the final step still passes (2 of the 10 plans we sampled after adding the rule were like that). Here that is harmless; with
executors that could not look things up themselves, such a step would fail visibly instead of being
rescued.

## Running it

```bash
uv run python -m examples.planner_executor.agent
```

To use it in your project:

```bash
uv run python scripts/add_agent.py planner_executor --name research
```

The cities are invented, so a model cannot know them and has to use `get_city`. To adapt it, replace
`get_city` and the executor's and planner's instructions (the planner is told what its executors can
do, which is how it plans only steps they can carry out), and keep `check_plan`, the scheduling loop
in `run_planner_executor`, and the failure handling.

`run_planner_executor` returns a `RunResult`: `.output` carries the answer (`result`, `subject`,
`value`), the `plan`, each step's `results`, the `waves`, and any `failed` / `skipped` steps; `.steps`
holds the planner, then each executor that finished, then the synthesizer. The tests are in
`examples/planner_executor/test_example.py`.
