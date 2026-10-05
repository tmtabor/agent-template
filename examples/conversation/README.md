# Conversation

An agent that remembers what was said, keeps its context bounded, and streams its replies.

**See it run:** [`sample_run.md`](sample_run.md) is a recorded run against a real model: what each agent was asked, which tools it called, and what it returned.

**Use it when** users talk to the agent over several turns and expect it to remember, a long
conversation shouldn't grow the context (and the bill) without limit, and replies should appear as
they are written.

```
turn 1 ─┐
turn 2 ─┼→ history ─→ (keep the last N turns) ─→ model ─→ reply ─→ history for the next turn
turn 3 ─┘
```

**What it shows**

- **Memory is message history:** each turn passes the earlier messages in, and the result's messages
  become the next turn's history. `Conversation` holds that for you
- **A bounded window:** a history processor (`ProcessHistory`) keeps the last `max_turns` user turns
  before every model request, reading the size from deps so each conversation can choose its own. It
  cuts only at turn boundaries, so a tool call is never separated from its result
- **Streaming:** `Conversation.stream()` yields the reply as text deltas and updates the history
  when it finishes. The agent returns plain text (no `output_type`), which is what streams; a
  structured output has no text to stream until it is complete
- **What it doesn't do:** once a turn leaves the window the model no longer sees it. That is
  context management, not long-term memory; to remember across sessions, store facts yourself and
  put them in the instructions

```bash
uv run python scripts/add_agent.py conversation --name assistant
```

`run_chat(text, deps, history=...)` is one turn and returns a `RunResult` like every other example;
`Conversation` is the convenient way to hold a dialogue:

```python
conversation = Conversation()  # or Conversation(ChatDeps(max_turns=6))
await conversation.say("My name is Priya.")
reply = await conversation.say("What is my name?")  # reply.output: "Your name is Priya."
async for delta in conversation.stream("Tell me a joke."):
    print(delta, end="")  # the reply, as it is generated
```
