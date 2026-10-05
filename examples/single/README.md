# Single agent

One agent handles the whole task. The simplest pattern and the lowest complexity.

**Use it when** one agent can do the full job and nothing needs specializing or delegating.

**What it shows**
- A structured output type (`AgentOutput`) and an injectable deps dataclass (`AgentDeps`)
- Instructions loaded from a prompt file (`prompts/single.txt`)
- `USAGE_LIMITS` as a guardrail on every run, and `RaiseContentFilterError`
- Commented recipes for tools, dynamic instructions and multi-turn history
- `test_example.py`: how to unit-test an agent with `TestModel`

```bash
uv run python scripts/add_agent.py single --name my_agent
```
