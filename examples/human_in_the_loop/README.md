# Human in the loop

Pause a risky action until a person approves it, reject impossible requests before anyone is asked,
and resume the same run with the decision.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

**Use it when** the agent can take actions with real consequences (money, deletions, messages),
some should wait for a human while others are fine alone, and a request that can't succeed
shouldn't cost anyone's attention.

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

```bash
uv run python scripts/add_agent.py human_in_the_loop --name refunds
```

To adapt it, replace the orders and `issue_refund` with your own action, keep the validate → defer →
resume shape, and replace `approver` with how your approvals really happen. The result has one step
for the run that paused and one for each run that resumed.
