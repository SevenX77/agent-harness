# Cognitive Loop Guide

Deep dive into `graph_agent`'s dual-layer cognitive control architecture.

---

## Overview

`GraphAgentHarness` implements a **dual-layer control** architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    OUTER HARNESS LAYER                       │
│  While-loop across phases: planning, nudge, selfcheck,      │
│  checkpoint compaction, finish gate                         │
├─────────────────────────────────────────────────────────────┤
│                      MIDDLEWARE LAYER                        │
│   Real-time intervention per agent.invoke():               │
│   working memory, dead-end pruning, clarification            │
├─────────────────────────────────────────────────────────────┤
│                    LANGCHAIN AGENT                          │
│   Core agent loop: LLM calls, tool execution, streaming      │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Planning Enforcement

**Goal**: Ensure agent externalizes its plan before executing business tools.

**Logic**:
1. First `agent.invoke()` returns
2. Check `_working_memory` in context
3. If **not updated** → inject `PLANNING_NUDGE`
4. If **updated** → set `plan_verified = True`

**PLANNING_NUDGE**:
```
[系统提示] 在执行任何业务工具之前，你必须先调用 update_working_memory 
记录你的执行计划。计划应包含：
1. 本阶段的目标是什么
2. 你打算按什么顺序执行哪些步骤
3. 每步需要什么数据（如果需要从上下文或工具获取，写明）
4. 预期产出是什么
请现在调用 update_working_memory。
```

**Why**: Forces explicit planning, enables plan validation later.

---

## 2. Selfcheck Enforcement

**Goal**: Ensure structured self-review at phase completion.

**Logic**:
1. `finish_task` tool is called
2. Check `_has_structured_selfcheck` flag
3. If **incomplete** → inject `SELFCHECK_NUDGE`
4. If **complete** → proceed to phase end

**SELFCHECK_NUDGE**:
```
[系统提示] 你调用了 finish_task，但自检结构不完整。
请重新调用 finish_task，并补全以下字段：
execution_summary、plan_checklist（数组，每项含 step/completed/quality_check）、
unresolved_issues。
请逐条对照计划说明质量结论后再 finish。
```

**finish_task structure**:
```python
{
    "execution_summary": str,        # Overall summary
    "plan_checklist": [              # Step-by-step review
        {
            "step": str,
            "completed": bool,
            "quality_check": str
        }
    ],
    "unresolved_issues": str,         # Known limitations
    "reasoning": str,                # Thought process
    "evidence": [str]                # Supporting evidence
}
```

---

## 3. Checkpoint Compaction

**Goal**: Manage context window by compressing message history.

**Trigger**: Working memory updated (via `update_working_memory`)

**Process**:
```
Before: [system, user, assistant1, tool1, assistant2, tool2, ...]
After:  [system, user, checkpoint_text]
```

**checkpoint_text** format:
```
[CHECKPOINT COMPACTED]
Previous working memory: <plan_text>
Last action summary: <action_result>
[END CHECKPOINT]
```

**Benefits**:
- Keeps context window manageable
- Preserves essential plan context
- Removes detailed tool call history

---

## 4. Standard Nudge

**Goal**: Recover when agent produces text output without tool calls.

**Trigger**: Last message is text-only (no tool_calls)

**Escalating levels**:

| Count | Severity | Message |
|-------|----------|---------|
| 1 | Gentle | "[系统提示] 你输出了文本但未调用 finish_task..." |
| 2 | Warning | "[系统警告] 这是第二次提醒..." |
| 3+ | Critical | "[严重警告] 你的行为已偏离规范..." |

**Logic**:
```python
if nudge_count == 1:
    nudge = GENTLE_PROMPT
elif nudge_count == 2:
    nudge = WARNING_PROMPT + f"无效输出: {content[:600]}"
else:
    nudge = CRITICAL_PROMPT
```

---

## 5. Nudge Budget

**Goal**: Prevent infinite nudge loops.

**Configuration** (per phase_config):
- `max_nudges`: Max nudges per type (default: 3)
- `total_nudge_count`: Global counter
- **Threshold**: `total_nudge_count >= max_nudges * 2`

**When exceeded**:
```python
if total_nudge_count >= max_nudges * 2:
    # Forced degrade: accept current output
    logger.warning("[NudgeBudget] Exceeded threshold, forced degrade")
    break  # Exit phase
```

---

## 6. Finish Gate

**Goal**: Ensure structured completion before phase end.

**Checks before phase completion**:
1. `_finish_task_result` exists in context
2. `execution_summary` is non-empty
3. `plan_checklist` is a list with at least one item
4. Each item has `step` and `completed` fields

**Incomplete finish_task** → Trigger SELFCHECK_NUDGE

---

## 7. Control Flow Diagram

```
Phase Start
    │
    ▼
┌─────────────────────────┐
│ First agent.invoke()    │
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│ _working_memory exists? │─NO─▶│ Inject PLANNING_NUDGE   │
└─────────────────────────┘     └─────────────────────────┘
    │YES                              │
    │                                 ▼
    │                          ┌─────────────────────────┐
    │                          │ Retry invoke()          │
    │                          └─────────────────────────┘
    │                                 │
    └─────────────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│ plan_verified = True    │
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│ Execute business tools  │◀───────┐
└─────────────────────────┘        │
    │                              │
    ▼                              │
┌─────────────────────────┐        │
│ Text-only output?       │─YES───▶│ Inject Standard Nudge
└─────────────────────────┘        │ (escalating levels)
    │NO                            │
    │                              │
    ▼                              │
┌─────────────────────────┐        │
│ finish_task called?     │─NO────▶│
└─────────────────────────┘        │
    │YES                           │
    │                              │
    ▼                              │
┌─────────────────────────┐        │
│ Structured selfcheck?   │─NO────▶│ Inject SELFCHECK_NUDGE
└─────────────────────────┘        │
    │YES                           │
    │                              │
    ▼                              │
┌─────────────────────────┐        │
│ Checkpoint compaction     │        │
│ (if working memory      │        │
│  updated)                 │        │
└─────────────────────────┘        │
    │                              │
    ▼                              │
┌─────────────────────────┐        │
│ Phase End               │────────┘
└─────────────────────────┘
```

---

## 8. Middleware Layer (Inner)

Middleware runs within each `agent.invoke()`:

| Middleware | Purpose |
|------------|---------|
| `WorkingMemoryMiddleware` | Injects working memory into context |
| `DeadEndPruningMiddleware` | Detects and prunes dead-end paths |
| `ClarificationMiddleware` | Handles clarification requests |
| `DanglingToolCallMiddleware` | Cleans up incomplete tool calls |

**Activation**: Configured via `create_custom_middlewares()` in harness.

---

## 9. Configuration

In SKILL.md phase_config:

```yaml
name: my_phase
tier: balanced
tools: [script.my_tools.process]
max_nudges: 5           # Custom nudge budget
dead_end_threshold: 10  # Dead end detection threshold
```

---

## 10. Observability

Key callback events:

| Event | Trigger |
|-------|---------|
| `on_nudge` | Standard nudge injected |
| `on_working_memory_update` | Working memory persisted |
| `on_finish_task` | Phase completion structured |
| `on_dead_end_pruned` | Dead-end path pruned |
| `on_compaction` | Checkpoint compaction occurred |

Enable tracing:
```python
from graph_agent import TracingCallback

tracer = TracingCallback(trace_dir="./traces")
result = run_skill(skill_path, callbacks=[tracer])
tracer.save("./traces")
```
