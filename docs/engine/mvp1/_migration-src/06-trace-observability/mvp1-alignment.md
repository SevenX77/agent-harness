---
module: 06-trace-observability
doc: mvp1-alignment
status: drafted
last_verified: 2026-06-02
---

# 06-trace-observability — MVP1 Alignment(目标设计)

MVP1/V4 决策：迁移到 create_agent 后 trace 覆盖不得回退。TracingMiddleware 要补回现有 loop 级 LLM/tool/iteration 事件；finish_task 校验流水线每个关键步骤都要发事件，让前端 trace 面板看到“做了什么、为什么被打回、是否 patch、是否 nudge”。

## 覆盖范围

覆盖范围：本文覆盖现有 trace 事件、TracingCallback、middleware skeleton、finish_task 黑盒消除目标。

| 范围 | MVP1 目标 |
|---|---|
| `callbacks/events.py` | 复用现有事件；必要时新增 V4 finish validation 事件。 |
| `callbacks/tracing.py` | 继续作为 trace.jsonl 主要 writer。 |
| `middleware/tracing.py` | 实现 create_agent 路径下的 LLM/tool/iteration emit。 |
| finish_task 校验链 | 每个分支发可解释事件。 |

## 目标设计与编号流程

1. `TracingMiddleware` 构造时接收 phase_name 与 callbacks/event sink。当前 skeleton 只有 phase_name，见 `packages/graph-agent/src/graph_agent/middleware/tracing.py:11-16`；MVP1 需要补 callbacks 依赖。

2. `TracingMiddleware.wrap_model_call` 或相关 hook 负责模型调用前后采集 token usage 和 response metadata，补发 `LLMCallEvent`。当前 hand-written loop 的 token extraction 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:513-524`，迁移后不能消失。

3. `TracingMiddleware.wrap_tool_call` 负责工具调用耗时、args、result 的 `ToolCallEvent`。当前 hand-written loop 只记录 result 字符串，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:547-555`；MVP1 可在此基础上补 duration。

4. `ExecutionControlMiddleware` 已经发 `AgentLoopIterationEvent`，见 `packages/graph-agent/src/graph_agent/middleware/execution_control.py:182-199`；TracingMiddleware 不应重复发同一 iteration，而应保证该事件在 live chain 里被接入 callbacks。

5. finish_task 提交时发 `FinishTaskEvent` 或 V4 专用提交事件。当前 `FinishTaskEvent` 字段是 reasoning/evidence，见 `packages/graph-agent/src/graph_agent/callbacks/events.py:105-109`；若 markdown/schema diagnostics 信息不足，应新增事件而不是塞不可解释字符串。

6. semantic-only reject 发 `ValidationFailEvent` 或专用 `FinishTaskValidationEvent(kind="semantic")`。丰富版 semantic-only 抛错点见 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:559-567`。

7. structural patch path 发 patch start/pass/fail。`md_to_json` 触发 patch 的代码在 `packages/graph-agent/src/graph_agent/tools/md_to_json.py:568-604`。

8. schema gate pass/fail 发 `ValidationPassEvent` / `ValidationFailEvent`。CognitiveFlow schema gate 当前在 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:241-252`。

9. business validator pass/fail 发 `ValidationPassEvent` / `ValidationFailEvent`，并把错误标成 business 层。当前 business validator 在 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:637-680`。

10. exit gate nudge 发 `NudgeEvent`。NudgeInjector 当前会通过 callback `on_nudge` 发 legacy/typed nudge，见 `packages/graph-agent/src/graph_agent/core/nudge_injector.py:189-206`；迁移后 exit gate 应沿用这条可观测性。

11. 所有事件通过 `_safe_emit_event` 或 callback `on_event` 发，避免 observer 异常打断 run。安全派发逻辑见 `packages/graph-agent/src/graph_agent/callbacks/emit.py:68-102`。

## 已实现 / 与 baseline 差异

已实现：事件模型、trace writer、safe emit、loop 内联事件都已存在，见 `packages/graph-agent/src/graph_agent/callbacks/events.py:73-116`、`packages/graph-agent/src/graph_agent/callbacks/tracing.py:183-350`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:305-555`。

未实现：TracingMiddleware no-op，见 `packages/graph-agent/src/graph_agent/middleware/tracing.py:11-16`。

未实现：finish_task 校验子步骤不发事件，相关流程见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:468-699`。

## 决策原因

trace 覆盖不回退，是因为 create_agent 迁移会移除当前 `_skill_node` 内联 emit 点。若 TracingMiddleware 没有先补上，前端会从“能看见模型/工具调用”退回黑盒。

finish_task 子步骤必须可见，是为了处理用户提出的“流式输出和 trace 完整性、覆盖率、去黑盒”要求。semantic reject、structural patch、business validator reject 是完全不同的系统行为，前端和排障都不能混成一句“validation failed”。

## 代码索引(clues)

- `packages/graph-agent/src/graph_agent/callbacks/tracing.py:183-350`: TracingCallback 已支持核心事件写入。
- `packages/graph-agent/src/graph_agent/middleware/execution_control.py:182-199`: AgentLoopIterationEvent 现有 emit。
- `packages/graph-agent/src/graph_agent/tools/md_to_json.py:559-604`: semantic/structural 分流发事件的目标位置。
- `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:637-680`: business validator 发事件目标位置。

## 待办/疑点

1. 待办：为 TracingMiddleware 写失败测试，证明 create_agent 路径仍产生 LLMCallEvent 和 ToolCallEvent。
2. 待办：决定是否新增 V4 `FinishTaskValidationEvent`，避免现有 `ValidationFailEvent` 信息不足。
3. 待办：前端 trace inspector 依赖字段需另行核对；本篇只定义 engine 事件覆盖。
4. 待办（studio 对齐 · 微观拓扑）：studio canvas REQ-13 要把 agent 节点黑盒展开成微观拓扑（`update_working_memory`/`tool_calls`/`LLM Reply`/`md2json`/`validator`/`finish_task`），需要**嵌套微观事件带 `parent_node_id`（=该 agent phase_id）/ `node_type`**。这正好是 TracingMiddleware 的天然产物——中间件的 `before_model`/`after_model`/`wrap_tool_call` 每一步都能 emit 带 `parent_node_id` 的子事件，无需额外引擎改动，只需把微观事件 schema（`parent_node_id`/`node_type` 嵌套）定义进 trace 契约。对齐源 `docs/studio/mvp1/01_workflows/04_execution.md` §2.4 + workflow-action-catalog canvas REQ-13。
5. 待办（studio 对齐 · **dot = 节点间状态机操作事件**，与 §5 同源）：trace-observability 定义 dot = 两节点之间的转移点，点 dot 要看"上节点 end→下节点 start 之间的**全部操作**"——黑板 reduce/聚合、**并联节点输入筛选/分发**、**文件注入→黑板**、**artifact 落盘**、截断/摘要/存储。现只有零散 `Compaction`/`ArtifactSaved`。需把这些"边上操作"成系列显式 emit（前端点 dot 才有完整操作记录，而非只有 PhaseEnd/PhaseStart 前后快照）。⚠️ 这些操作正是 `09/10` 之后 §5 要设计的运行时改动（文件注入→黑板 G2/FROZEN-3、artifact 落盘 G3），**设计 §5 时一并定义其 trace 事件**。对齐源 `docs/studio/mvp1/02_capabilities/trace-observability.md` §2 + `engine-prompt-trace-compile-debug.md` §三-1。
6. 待办（reducer 级前后态 diff，REQ-7）：权威"哪个 reducer 改了哪个 key"的 diff，引擎 emit vs 前端用 `PhaseEnd[A].context` vs `PhaseStart[B].context` 近似——待定（engine-prompt §三-3）。
7. 待办（Prompt 三视图）：核实 `PromptCapturedEvent` 是否同时带 模板 / 喂入变量 / 渲染后；若只有渲染后（=LLMCall.messages）需补模板+变量（engine-prompt §三-4）。
8. 待办（嵌套子图链路）：微观事件 + 嵌套子图需带 `parent_node_id` / `node_type` / 嵌套路径；现 `phase_name + run_id` 是否够、还是需显式父链路——实现期定（engine-prompt §三-2）。
9. 待办（**多轮 trace 不丢失 · 2026-06-03 PM 定**）：节点因 loop/retry/batch/resume 多次执行时，前端 focus 该节点要看**全部轮次**，不能只取最近一次。事件 schema 须加 **`phase_execution_id`**（每次节点整体执行实例唯一，前端按它分组成"轮"）+ 语义标签 **`iteration_index`**（loop/batch 第几项/轮）、**`attempt`**（校验/nudge 重试第几次）、**`source`**（run/loop/batch/retry/resume）。归属层级：`phase_name`（哪个节点）→ `phase_execution_id`（哪一轮）→ 轮内 `AgentLoopIterationEvent`/微观 `parent_node_id`。盖戳的执行器在 `10-iteration-and-resume`（§3 已登记，含 batch per-item 归属修复）。对齐源 `trace-observability.md` §3/§5。

