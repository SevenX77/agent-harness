---
module: 01-agent-loop
doc: baseline
status: drafted
last_verified: 2026-06-02
---

# 01-agent-loop — Baseline(现状)

核心结论：当前 SDK 主入口仍走 `assemble_graph` 里的手写 ReAct loop；仓库中另有 `LLMPhaseNode` 这条 `create_agent` 风格代码，但当前 `run_skill` / `predict_skill` 的 live 路径没有通过它。完整 6 槽 middleware 工厂已存在，live 只临时接了 `CognitiveFlowMiddleware` 单槽。

## 覆盖范围

覆盖范围：本文覆盖决策记录 §1、§2、§3 对应的现状代码。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| `core/runner.py:run_skill` / `_run_v030_skill_dict` | `packages/graph-agent/src/graph_agent/core/runner.py:386-453`、`packages/graph-agent/src/graph_agent/core/runner.py:623-690` | 证明当前 SDK 执行入口仍编译后调用 `assemble_graph`。 |
| `core/graph_assembler.py:assemble_graph` | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:88-151` | 编译 V0.3.0 skill 到 LangGraph `StateGraph`。 |
| `core/graph_assembler.py:_build_skill_node` | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:423-578` | 当前 agent phase 的 live 手写 ReAct loop。 |
| `middleware/factory.py:build_middleware_chain` | `packages/graph-agent/src/graph_agent/middleware/factory.py:29-65` | 6 槽 `AgentMiddleware` 链已可构造，但没有接入 live loop。 |
| `middleware/__init__.py:MVP0_MIDDLEWARE_ORDER_CONTRACT` | `packages/graph-agent/src/graph_agent/middleware/__init__.py:58-65` | 6 槽顺序契约。 |
| 3 个 middleware 空桩 | `packages/graph-agent/src/graph_agent/middleware/tracing.py:11-16`、`packages/graph-agent/src/graph_agent/middleware/tool_error.py:11-16`、`packages/graph-agent/src/graph_agent/middleware/loop_detection.py:11-16` | Tracing / ToolError / LoopDetection 只是物理 no-op 类。 |
| 并存 `LLMPhaseNode` | `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:105-128`、`packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:559-576` | 已有 create_agent 风格路径，但非当前 SDK 主入口。 |

## 编号执行流程(现状)

1. `run_skill`(用途：执行 SKILL.md 并返回 typed workflow result)先调用 `_run_skill_dict`，见 `packages/graph-agent/src/graph_agent/core/runner.py:401-415`。

2. `_run_skill_dict`(用途：按 skill root 选择执行路径)发现目录里有 `GRAPH.md` 时进入 `_run_v030_skill_dict`，见 `packages/graph-agent/src/graph_agent/core/runner.py:498-511`。

3. `_run_v030_skill_dict`(用途：执行 V0.3.0 skill root)在运行期解析 checkpointer，然后调用 `compile_skill` 和 `assemble_graph`，见 `packages/graph-agent/src/graph_agent/core/runner.py:637-674`。

4. `assemble_graph`(用途：把 `CompiledSkill` 装配成 LangGraph)遍历拓扑并为每个 phase 调 `_build_phase_node`，最后 `builder.compile(checkpointer=checkpointer)`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:111-151`。

5. `_build_phase_node`(用途：按 AST 类型选择 phase runtime node)遇到 `AgentNodeAST` 时调用 `_build_skill_node`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:201-221`。

6. `_build_skill_node`(用途：构造 agent phase 的实际执行闭包)先解析模型、reference reader、业务工具、subagent 工具和 framework tools，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:437-479`。

7. `_build_skill_node` 当前只调用 `build_middleware_chain_cognitive_flow(phase_name=phase_id)`，拿到的是单个 `CognitiveFlowMiddleware`，不是完整 6 槽链，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:481` 与 `packages/graph-agent/src/graph_agent/middleware/factory.py:68-92`。

8. `_skill_node`(用途：当前 agent phase 的 live loop)手动构造 `SystemMessage + state["messages"]`，再通过 `_bind_tools_if_supported` 让模型绑定工具，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:497-508`。

9. `_skill_node` 用 `for _ in range(max_turns)` 控制 ReAct turn，调用 `model.invoke(prompt_messages)`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:510-513`。

10. `_skill_node` 在每次模型调用后发 `LLMCallEvent`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:515-524`。

11. `_skill_node` 读取 `response.tool_calls`；如果没有 tool_calls，直接 `break`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:525-528`。这就是当前裸退点。

12. `_skill_node` 对未知工具直接 fatal，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:529-533`。

13. `_skill_node` 对 subagent 工具走 `_invoke_subagent_tool_t21` 特判，对普通工具直接 `tool.invoke(call_args)`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:535-546`。

14. `_skill_node` 在工具执行后发 `ToolCallEvent` 并追加 `ToolMessage`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:547-562`。

15. `_skill_node` 每个工具结果都调用 `cognitive_flow.handle_finish_task_tool_result`；只有 finish_task 通过该桥接返回时才结束 phase，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:563-572`。

16. `build_middleware_chain`(用途：实例化 6 槽 AgentMiddleware 链)已经能按 `MVP0_MIDDLEWARE_ORDER_CONTRACT` 返回 `ProtocolValidation`、`CognitiveFlow`、`ExecutionControl`、`Tracing`、`ToolError`、`LoopDetection` 六个实例，见 `packages/graph-agent/src/graph_agent/middleware/factory.py:29-65`。

17. `MVP0_MIDDLEWARE_ORDER_CONTRACT`(用途：固定 6 槽顺序)写明顺序为 `ProtocolValidation`、`CognitiveFlow`、`ExecutionControl`、`Tracing`、`ToolError`、`LoopDetection`，见 `packages/graph-agent/src/graph_agent/middleware/__init__.py:58-65`。

18. `ProtocolValidationMiddleware`(用途：在模型前后守住 state contract)已实现 `before_model` / `after_model`，见 `packages/graph-agent/src/graph_agent/middleware/protocol_validation.py:102-132`。

19. `CognitiveFlowMiddleware`(用途：截获 finish_task 与 ask_clarification)已实现 `wrap_tool_call`，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:348-390`。

20. `ExecutionControlMiddleware`(用途：迭代计数、dead-end、轻量 loop 检测)已实现 `before_model` / `after_model`，见 `packages/graph-agent/src/graph_agent/middleware/execution_control.py:120-154`。

21. `TracingMiddleware`、`ToolErrorHandlingMiddleware`、`LoopDetectionMiddleware` 当前只有构造函数和 phase name 字段，是 no-op skeleton，见 `packages/graph-agent/src/graph_agent/middleware/tracing.py:11-16`、`packages/graph-agent/src/graph_agent/middleware/tool_error.py:11-16`、`packages/graph-agent/src/graph_agent/middleware/loop_detection.py:11-16`。

22. `LLMPhaseNode`(用途：旧 PhaseExecutor 路径下的 create_agent 风格 LLM phase)确实会创建 `create_agent(model, tools, system_prompt, middleware)`，见 `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:559-576`；但当前 SDK V0.3.0 root 入口不经 `GraphBuilder/PhaseExecutor`，而经 `assemble_graph`，见 `packages/graph-agent/src/graph_agent/core/runner.py:667-674`。

## Baseline / Alignment 差异

baseline 当前是“手写 loop + 单槽 CognitiveFlow 桥接 + 完整 6 槽工厂未接线”。alignment 目标是“live `_skill_node` loop 体替换为 `create_agent(..., middleware=build_middleware_chain(...), checkpointer=...)`，并把 3 个 no-op 空桩实现为真实 middleware”。

## 决策原因

当前不能把 `LLMPhaseNode` 当作已完成迁移，因为 live `run_skill` 和 `predict_skill` 均通过 `assemble_graph` 装配，见 `packages/graph-agent/src/graph_agent/core/runner.py:276-283`、`packages/graph-agent/src/graph_agent/core/runner.py:667-674`。

当前不能只说“middleware 已经好了”，因为 `build_middleware_chain` 返回 6 槽，但 `_build_skill_node` 只拿了 `build_middleware_chain_cognitive_flow` 的单槽结果，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:481`。

当前 no-tool-call 裸退是 agent loop 架构冲突的核心证据：`tool_calls` 为空时直接 `break`，没有 finish_task 合格性检查，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:526-528`。

## 代码索引(clues)

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:483-576`: `_skill_node` 是当前 live 手写 ReAct loop。
- `packages/graph-agent/src/graph_agent/middleware/factory.py:29-65`: `build_middleware_chain` 是 6 槽 AgentMiddleware 工厂。
- `packages/graph-agent/src/graph_agent/middleware/__init__.py:58-65`: `MVP0_MIDDLEWARE_ORDER_CONTRACT` 是顺序单一事实来源。
- `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:570-575`: 并存 create_agent 调用点。
- `packages/graph-agent/tests/middleware/test_aaa_beta_red_light_factory.py:12-35`: 测试已锁定 6 槽工厂顺序。

## 待办/疑点

1. 待办：把 `assemble_graph` 的 agent phase live path 接到 `create_agent`，同时保留 phase 级模型解析、工具装配、reference reader、subagent 编译缓存。
2. 待办：实现 Tracing / ToolError / LoopDetection 三个 no-op 空桩。
3. 疑点：`LLMPhaseNode` 是旧 PhaseExecutor 路径的并存代码，MVP1 实现时应决定复用其局部逻辑还是收口到 `graph_assembler`，避免第三条 loop 路线继续分裂。

