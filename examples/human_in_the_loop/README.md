# Human in the loop

Pause a risky action until a person approves it, reject impossible requests before anyone is asked, and resume the same run with the decision.

Some actions an agent can take should not happen on the model's say-so alone: a refund, a deletion, a message sent in your name. Here a tool can pause the run. Instead of acting, it asks for approval and the run stops. A person (or a policy, or a queue you build) decides, and the same run resumes with that decision; if it was denied, the model is told, so it can explain. Requests that can't succeed are rejected first, so nobody is asked about something impossible, and the agent's own claims are checked against a ledger of what really happened.

**Use it when**

- The agent can take actions with real consequences: money, deletions, messages.
- Some of them should wait for a human and others are fine on their own.
- A request that can't succeed shouldn't cost anyone's attention.

**Look elsewhere when**

- Every action is safe or reversible: the pause only adds delay.
- You need to filter what users send in, not approve what the agent does: [`guardrails`](../guardrails/).

```
request → tool call → validate
                        ├─ impossible → rejected; no human is asked
                        ├─ small      → runs
                        └─ large      → PAUSE → approver → resume → answer
```

**What it shows**

- **Three outcomes from one tool** (`issue_refund`): refunds up to `AUTO_APPROVE_LIMIT_USD` run on
  their own; larger ones raise `ApprovalRequired` and the run *pauses*, returning
  `DeferredToolRequests` instead of acting; impossible ones (unknown order, shipped, over the
  total) are rejected first
- **Validation before approval:** `args_validator` runs before the approval gate, so a human is only
  ever asked about a request that could really happen
- **A pluggable approver:** `run_refunds` asks `deps.approver` about each pending call, then resumes
  the same conversation with `DeferredToolResults`. A denial is passed to the model as a
  `ToolDenied` message so it can explain. `deny_all` is the default (nothing risky happens
  unconfigured); `console_approver` asks a person at the terminal; swap in a Slack message, a ticket
  queue or a policy
- **The ledger is the truth:** `deps.refunds` records what really happened, and an output validator
  rejects a claim that doesn't match it (`refunded=True` with an empty ledger is sent back to the
  model), so the agent can't say it did something it didn't
- A run that keeps asking for approval is stopped after `MAX_APPROVAL_ROUNDS`

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

```bash
uv run python scripts/add_agent.py human_in_the_loop --name refunds
```

To adapt it, replace the orders and `issue_refund` with your own action, keep the validate → defer →
resume shape, and replace `approver` with how your approvals really happen. The result has one step
for the run that paused and one for each run that resumed.
