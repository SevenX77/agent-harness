# graph_agent Examples

This directory contains example skills demonstrating `graph_agent` capabilities.

## Quick Start

> Public SDK: `from graph_agent import run_skill, GraphAgentHarness, SkillManifest, ...` (see `graph_agent/__init__.py` for the 12 public exports).

### 1. Hello World (Minimal Example)

**Purpose**: Verify graph_agent installation and basic functionality.

**Location**: `hello_world/`

**Structure**:
```
hello_world/
├── SKILL.md          # Skill definition
└── script/
    └── greet.py      # Simple greet tool
```

**Run**:
```bash
# From project root (uv workspace handles the path)
uv run python3 -c "
from graph_agent import run_skill

result = run_skill(
    'packages/graph-agent/src/graph_agent/examples/hello_world/SKILL.md',
    initial_context={'user_name': 'Developer'}
)
print('Result:', result)
"
```

**Expected output**:
```
Result: {'greeting': 'Hello, Developer! Welcome to graph_agent.', ...}
```

**What it demonstrates**:
- Simple mode skill
- Tool calling with context
- finish_task integration
- Phase completion

---

## Example Categories

| Example | Status | Description |
|---------|--------|-------------|
| hello_world | ✅ Ready | Minimal verification example |

---

## Creating New Examples

To add a new example:

1. Create directory: `examples/my_example/`
2. Add `SKILL.md` with skill definition
3. Add tools in `script/` subdirectory
4. Update this README

### Example SKILL.md Template

```yaml
---
name: my-example
description: Description of what this example demonstrates
type: simple
---

<phase_config>
name: my_phase
llm_role: analyst
tools:
  - script.my_tools.my_function
</phase_config>

<system_prompt>
Your system prompt here.
</system_prompt>

<user_prompt>
Your user prompt here.
</user_prompt>
```

### Example Tool Template

```python
"""Tool description."""
from __future__ import annotations

from typing import Any


def my_tool(ctx: dict[str, Any]) -> str:
    """Tool docstring."""
    # Access context
    value = ctx.get("some_key", "default")
    
    # Process and return
    result = f"Processed: {value}"
    ctx["result_key"] = result
    return result
```

---

## Running Examples

All examples assume:
1. Dependencies installed from `requirements.txt`
2. `config/llm_roles.yaml` provided
3. API keys configured in `.env`

### With Tracing

```python
from graph_agent import run_skill, TracingCallback

tracer = TracingCallback(trace_dir="./traces")
result = run_skill(
    'examples/hello_world/SKILL.md',
    callbacks=[tracer]
)
tracer.save("./traces")
```

### With Custom Context

```python
initial_context = {
    'user_name': 'Alice',
    'project_id': 'proj-123'
}

result = run_skill(
    'examples/hello_world/SKILL.md',
    initial_context=initial_context
)
```
