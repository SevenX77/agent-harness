---
module: 01-agent-loop
doc: mvp1-alignment
status: drafted
last_verified: 2026-06-02
---
<!-- 核对进度:已迁 7 块 / 未迁 0 块 / 2026-06-04 -->

~~# 01-agent-loop — MVP1 Alignment(目标设计)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md#2-数据流--机制)

MVP1/V4 目标：把当前 live 手写 ReAct loop 迁回 LangChain `create_agent`，并把 engine 已有 6 槽 middleware 链真实接入运行时。迁移不是重写 skill 编译、gateway 调用或 frozen skill-spec；它只收口 agent phase 的 loop 编排。

~~## 覆盖范围~~ → ✅[已迁入](../../02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md#2-数据流--机制)

覆盖范围：本文覆盖手写 loop 替换、6 槽接线、3 个空桩实现、deepagents/deerflow 借鉴边界。

| 范围 | MVP1 目标 |
|---|---|
| `core/graph_assembler.py:_build_skill_node` | 保留模型解析、工具集合、subagent runtime map、prompt 构建；替换内部 `_skill_node` 手写 loop。 |
| `middleware/factory.py:build_middleware_chain` | 从测试可构造变成 live `create_agent(middleware=...)` 输入。 |
| `middleware/tracing.py` | 实现 loop 级 LLM/tool/iteration trace，不让迁移后现有事件消失。 |
| `middleware/tool_error.py` | 把工具异常转为 error `ToolMessage`，让 LLM 有机会恢复。 |
| `middleware/loop_detection.py` | 在 ExecutionControl 轻量检测之外实现更完整的 loop 保护，避免重复。 |

~~## 目标设计与编号流程~~ → ✅[已迁入](../../02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md#2-数据流--机制)

1. `_build_skill_node`(用途：构造 agent phase 的实际执行闭包)继续负责 phase 本地上下文：`_resolve_phase_chat_model`、reference reader、业务工具、subagent runtime map、finish_task 工具、system prompt，这些现状入口在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:437-479`。

2. `_skill_node` 的手写 `for _ in range(max_turns)` loop 替换为一次 `create_agent` 构造和一次 `agent.invoke`。本地 LangChain `create_agent` 签名支持 `model`、`tools`、`system_prompt`、`middleware`、`checkpointer`，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:658-673`。

3. `system_prompt` 继续消费 `_agent_system_prompt` 生成的一次性 V0.3.0 prompt。`create_agent` 会把 `system_prompt` 放在消息列表开头，见本地 LangChain 说明 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:706-709`。

4. `tools` 仍由 `business_tools + framework_tools + finish_task + subagent tools` 组成。当前 `all_tools` 构造点在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:479-480`，迁移后应把这组工具直接交给 `create_agent`，不再手动 `bind_tools`。

5. `middleware` 使用 `build_middleware_chain(...)`，不是当前的 `build_middleware_chain_cognitive_flow(...)`。6 槽工厂已经返回 `tuple[AgentMiddleware, ...]`，见 `packages/graph-agent/src/graph_agent/middleware/factory.py:29-65`。

6. `checkpointer` 继续从外层 `assemble_graph(..., checkpointer=...)` 传入，现状编译 StateGraph 时已经传给 `builder.compile(checkpointer=checkpointer)`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:150-151`。迁移到 `create_agent` 时应明确是否给 phase agent 内层也传同一个 checkpointer，详见 `records/uncovered-areas.md`。

7. `ProtocolValidationMiddleware` 保持第一槽。它守住 `BusinessData` 无 `_` 前缀、`FrameworkState` extra forbid、可选 schema validation，当前实现见 `packages/graph-agent/src/graph_agent/middleware/protocol_validation.py:134-210`。

8. `CognitiveFlowMiddleware` 保持第二槽。它已经能在 `wrap_tool_call` 截获 `finish_task` 与 `ask_clarification`，当前代码会用 `Command(goto=END)` 或 `Command(goto="model")` 控制流向，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:348-390`、`packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:468-512`。MVP1 成功 finish_task 路径不得继续 `goto=END`，因为 `../04-exit-control/mvp1-alignment.md` 已实证该跳转会绕过 after_agent 退出闸。

9. `ExecutionControlMiddleware` 保持第三槽。它已经在 `before_model` 发 `AgentLoopIterationEvent`，在 `after_model` 检测 dead-end 和轻量 loop，见 `packages/graph-agent/src/graph_agent/middleware/execution_control.py:120-154`。

10. `TracingMiddleware` 实现后应覆盖现在 `graph_assembler` 内联发的 `LLMCallEvent`、`ToolCallEvent` 和 iteration 事件。当前内联事件证据见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:515-524`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:547-555`。

11. `ToolErrorHandlingMiddleware` 实现后应参考 deerflow “tool 异常转 error ToolMessage”模式。LangChain middleware 文档说明 `wrap_tool_call` 异常默认会传播，见 `.venv/lib/python3.12/site-packages/langchain/agents/middleware/types.py:649-660`；deerflow 参考实现见 `temp/deerflow/backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py:21-67`。

12. `LoopDetectionMiddleware` 实现前必须先复核 ExecutionControl 已有轻量 loop/dead-end，避免重复注入同类提示。ExecutionControl 的轻量实现见 `packages/graph-agent/src/graph_agent/middleware/execution_control.py:243-316`；deerflow 更完整实现的设计说明见 `temp/deerflow/backend/packages/harness/deerflow/agents/middlewares/loop_detection_middleware.py:1-38`。

13. `model=` 必须继续吃 gateway A' 的 `GatewayChatModel` 编排外壳，而不是 engine 自己处理 provider 差异。当前 `_resolve_phase_chat_model` 通过 `model_resolver.resolve(...)` 拿模型，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:581-603`。

~~## 已实现 / 与 baseline 差异~~ → ✅[已迁入](../../02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md#2-数据流--机制)

已实现：6 槽顺序契约、6 槽工厂、前三槽真实类和后三槽物理类都在源码里。证据见 `packages/graph-agent/src/graph_agent/middleware/__init__.py:58-65` 与 `packages/graph-agent/src/graph_agent/middleware/factory.py:29-65`。

已实现：`CognitiveFlowMiddleware` 已经是 LangChain `AgentMiddleware` 风格，有 `wrap_tool_call` 和 async 对应方法，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:348-429`。

未实现：live `_skill_node` 尚未调用 `create_agent`，仍手写 `model.invoke` / `tool.invoke` / `ToolMessage` 拼接，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:510-562`。

未实现：后三槽目前 no-op，不能承担 trace、工具异常或 loop 保护，见 `packages/graph-agent/src/graph_agent/middleware/tracing.py:11-16`、`packages/graph-agent/src/graph_agent/middleware/tool_error.py:11-16`、`packages/graph-agent/src/graph_agent/middleware/loop_detection.py:11-16`。

~~## 决策原因~~ → ✅[已迁入](../../02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md#2-数据流--机制)

采用 `create_agent + middleware`，是因为 LangChain 当前 API 已经提供工具循环、middleware hook、checkpointer 与 jump 能力；继续手写 loop 会重复处理 tool-call 消息配对、return-direct、middleware 顺序和 checkpoint 交互。

不把 `LLMPhaseNode` 视为完成迁移，是因为当前 SDK V0.3.0 root 入口实际调用 `assemble_graph`，见 `packages/graph-agent/src/graph_agent/core/runner.py:667-674`。MVP1 的文档和实现应收口 live path，而不是继续保留双路线。

接入完整 6 槽链，是为了化解 scoping 里的 agent loop 架构冲突：当前只有 CognitiveFlow 单槽桥接，导致 trace、tool error、loop detection 的职责散落或缺失。

~~## 代码索引(clues)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md#2-数据流--机制)

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:483-576`: 需要替换的 live 手写 ReAct loop。
- `packages/graph-agent/src/graph_agent/middleware/factory.py:29-65`: 目标 live middleware 链构造器。
- `packages/graph-agent/src/graph_agent/middleware/execution_control.py:120-154`: 已实现的 before/after model 操作层。
- `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:658-673`: 本地 create_agent 支持的参数。
- `.venv/lib/python3.12/site-packages/langchain/agents/middleware/types.py:625-660`: after_agent / wrap_tool_call hook 形态。

~~## 待办/疑点~~ → ✅[已迁入](../../02-mechanism/05-run-inner/01-agent-loop/mvp1-alignment.md#2-数据流--机制)

1. 待办：实现前写失败测试，证明 live `assemble_graph` 的 agent phase 会调用 `create_agent` 且传入 6 槽 middleware。
2. 待办：保留现有 `LLMCallEvent` / `ToolCallEvent` 覆盖，不允许迁移后 trace 变少。
3. 待办：D-test-3 覆盖 `create_agent(model=GatewayChatModel)` 端到端编排，验证 gateway usage、thinking blocks、tool-call metadata 不因 engine 迁移丢失；模型入口证据见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:581-603`。
4. ~~疑点：内外两层 checkpointer 是否共用同一个 saver~~ → **已收口**：agent loop = 内层图,经 `checkpoint_ns="<phase_id>/agent"` 挂进**同一个** checkpointer(不另起 saver),每 model/tool 步存档以支撑 mid-conversation HITL。权威设计见 `records/state-checkpoint-storage-model §2.2`(CK1/CK2);嵌套 ns 寻址续跑的实测 = 该篇 §5.3 D-test(承 `records/uncovered-areas.md` #3)。
