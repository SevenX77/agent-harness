---
module: 06-trace-observability
doc: baseline
status: drafted
last_verified: 2026-06-02
---
<!-- 核对进度:已迁 7 块 / 未迁 0 块 / 2026-06-04 -->

~~# 06-trace-observability — Baseline(现状)~~ → ✅[已迁入](../../02-mechanism/06-seam/02-observability/baseline.md#后端功能)

核心结论：事件类型和 trace sink 已经丰富，live 手写 loop 也发了 phase/LLM/tool 事件；但 finish_task 校验子步骤基本是黑盒。`CognitiveFlowMiddleware`、`cognitive/finish_task.py`、`cognitive/md2json.py`、`cognitive/md_patch.py` 当前没有发 finish/validation/patch/nudge 细分事件。

~~## 覆盖范围~~ → ✅[已迁入](../../02-mechanism/06-seam/02-observability/baseline.md#后端功能)

覆盖范围：本文覆盖决策记录 §8。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| 事件类型 | `packages/graph-agent/src/graph_agent/callbacks/events.py:73-116`、`packages/graph-agent/src/graph_agent/callbacks/events.py:280-370` | LLM/tool/validation/finish/nudge/iteration 等类型已定义。 |
| trace callback | `packages/graph-agent/src/graph_agent/callbacks/tracing.py:183-350` | TracingCallback 能写 LLM/tool/validation/finish/nudge 事件。 |
| safe emit | `packages/graph-agent/src/graph_agent/callbacks/emit.py:68-102` | 统一安全派发 typed events。 |
| live loop emit | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:305-319`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:515-555` | phase、LLM、tool 事件在 hand-written loop 发出。 |
| middleware tracing skeleton | `packages/graph-agent/src/graph_agent/middleware/tracing.py:11-16` | TracingMiddleware 仍是 no-op。 |

~~## 编号执行流程(现状)~~ → ✅[已迁入](../../02-mechanism/06-seam/02-observability/baseline.md#后端功能)

1. `LLMCallEvent` 与 `ToolCallEvent` 已定义，payload 包含 phase、token、messages、response、tool args/result/duration，见 `packages/graph-agent/src/graph_agent/callbacks/events.py:73-88`。

2. `ValidationFailEvent`、`RetryEvent`、`FinishTaskEvent`、`NudgeEvent` 已定义，见 `packages/graph-agent/src/graph_agent/callbacks/events.py:91-116`。

3. `ValidationPassEvent`、`RetryExhaustedEvent`、`AgentLoopIterationEvent` 也已定义，见 `packages/graph-agent/src/graph_agent/callbacks/events.py:280-294`、`packages/graph-agent/src/graph_agent/callbacks/events.py:359-370`。

4. `TracingCallback.on_llm_call`(用途：记录 LLM 调用)会累计 token、写 legacy event、写 typed `LLMCallEvent`，见 `packages/graph-agent/src/graph_agent/callbacks/tracing.py:183-227`。

5. `TracingCallback.on_tool_call`(用途：记录工具调用)会写 typed `ToolCallEvent`，见 `packages/graph-agent/src/graph_agent/callbacks/tracing.py:229-267`。

6. `TracingCallback.on_validation_fail`、`on_retry`、`on_finish_task`、`on_nudge` 已能写对应 typed events，见 `packages/graph-agent/src/graph_agent/callbacks/tracing.py:268-350`。

7. `_safe_emit_event`(用途：派发 typed callback event 且不让 callback 异常中断 run)支持 sink、callable、callback list 三种形式，见 `packages/graph-agent/src/graph_agent/callbacks/emit.py:68-102`。

8. `_wrap_phase_runtime_node` 在每个 phase 入口发 `PhaseStartEvent`，finally 里发 `PhaseEndEvent`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:304-320`。

9. `_skill_node` 每次模型调用后发 `LLMCallEvent`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:515-524`。

10. `_skill_node` 每次工具调用后发 `ToolCallEvent`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:547-555`。

11. `ExecutionControlMiddleware` 已能在 `before_model` 发 `AgentLoopIterationEvent`，见 `packages/graph-agent/src/graph_agent/middleware/execution_control.py:120-134`、`packages/graph-agent/src/graph_agent/middleware/execution_control.py:182-199`。

12. `TracingMiddleware` 当前只是 no-op skeleton，见 `packages/graph-agent/src/graph_agent/middleware/tracing.py:11-16`。

13. `CognitiveFlowMiddleware` 内部 finish_task 校验、schema gate、business validator、reject/accept 流程没有 `_safe_emit_event` 或 callback emit 调用；当前相关逻辑在 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:468-699`。

14. `cognitive/finish_task.py`、`cognitive/md2json.py`、`cognitive/md_patch.py` 当前也没有 trace emit；其核心流程分别在 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:40-93`、`packages/graph-agent/src/graph_agent/cognitive/md2json.py:26-38`、`packages/graph-agent/src/graph_agent/cognitive/md_patch.py:65-84`。

~~## Baseline / Alignment 差异~~ → ✅[已迁入](../../02-mechanism/06-seam/02-observability/baseline.md#后端功能)

baseline 有事件基础设施和 loop 级事件，但 finish_task 校验链不可见。alignment 目标是实现 TracingMiddleware，并给 finish_task 校验流水线补发事件，迁移后覆盖率不能低于当前 hand-written loop。

~~## 决策原因~~ → ✅[已迁入](../../02-mechanism/06-seam/02-observability/baseline.md#后端功能)

trace 覆盖是验收标准，不是锦上添花。当前迁移如果只把 `_skill_node` 改成 create_agent，却不实现 TracingMiddleware，就会丢掉 `LLMCallEvent` 和 `ToolCallEvent` 的 live emit 点，见现状 emit 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:515-555`。

finish_task 校验黑盒会让前端无法解释“为什么被打回”：是 semantic-only、structural patch、schema gate、business validator 还是 exit gate nudge。现有事件类型已经足够承载这些节点，只是未发。

~~## 代码索引(clues)~~ → ✅[已迁入](../../02-mechanism/06-seam/02-observability/baseline.md#后端功能)

- `packages/graph-agent/src/graph_agent/callbacks/events.py:73-116`: 核心 trace 事件类型。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:515-555`: live LLM/tool emit。
- `packages/graph-agent/src/graph_agent/middleware/tracing.py:11-16`: no-op tracing slot。
- `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:468-699`: finish_task 黑盒流程。

~~## 待办/疑点~~ → ✅[已迁入](../../02-mechanism/06-seam/02-observability/baseline.md#后端功能)

1. 待办：TracingMiddleware 接管 LLMCall/ToolCall/AgentLoopIteration emit。
2. 待办：finish_task 校验链补事件：submitted、semantic_reject、structural_patch_start/pass/fail、schema_gate_pass/fail、business_validator_pass/fail、exit_gate_nudge。
3. 疑点：现有 `FinishTaskEvent` 字段只有 reasoning/evidence，是否足够表达 markdown/schema diagnostics；可能需要 V4 新事件或扩展字段。

