---
module: 04-exit-control
doc: baseline
status: drafted
last_verified: 2026-06-02
---

# 04-exit-control — Baseline(现状)

核心结论：当前 live 手写 loop 对“模型没有 tool_calls”直接 `break`，没有 after_agent 退出闸。NudgeInjector 已存在，但只作为旧 nudge 机制的策略对象；live `graph_assembler` agent loop 没有用它。CognitiveFlow 能接受/驳回 finish_task，但无法拦截无 tool_calls 自然结束。

## 覆盖范围

覆盖范围：本文覆盖决策记录 §6 的退出控制现状。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| no tool_calls 裸退 | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:510-528` | 手写 loop 空 tool_calls 直接 break。 |
| finish_task 接受/驳回 | `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:198-269`、`packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:468-512` | 只处理 finish_task tool result，不处理自然 END。 |
| NudgeInjector | `packages/graph-agent/src/graph_agent/core/nudge_injector.py:75-151` | 有 planning/selfcheck/standard nudge 逻辑。 |
| nudge 文本 | `packages/graph-agent/src/graph_agent/cognitive/finish.py:118-134` | 标准 nudge 文本要求调用工具或 finish_task。 |
| create_agent API 能力 | 本地 LangChain | `after_agent` 支持 `can_jump_to`，并在正常退出路径里位于 END 前。 |

## 编号执行流程(现状)

1. `_skill_node` 使用 `max_turns = phase_ast.max_iterations` 控制外层 loop，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:510-511`。

2. 每轮调用 `model.invoke(prompt_messages)` 后把 response 追加到 messages，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:513-525`。

3. `tool_calls = list(getattr(response, "tool_calls", []) or [])` 为空时，当前直接 `break`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:526-528`。

4. break 后 `_skill_node` 返回 `{"flow": flow, "messages": messages}`，如果没有 finish_task 接受结果，不会写入业务 data，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:573-576`。

5. `CognitiveFlowMiddleware.handle_finish_task_tool_result` 只有 tool name 是 `finish_task` 时才处理；否则返回 None，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:198-210`。

6. 如果 finish_task 返回 `ok=False`，`handle_finish_task_tool_result` 只返回 flow/messages，让 loop 继续，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:226-228`。

7. 如果 finish_task schema gate 或 validator 失败，CognitiveFlow 会把 tool message 追加回 messages，再返回 flow/messages，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:241-262`。

8. 如果 finish_task 通过，CognitiveFlow 用 `_finish_task_accept_response` 生成最终 state 更新，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:264-269`。

9. `CognitiveFlowMiddleware._handle_finish_task` 在 create_agent middleware 路径里通过 `Command(..., goto=END)` 结束，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:468-512`；其中 `END` 从 `langgraph.graph` 导入，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:31`。

10. `NudgeInjector.try_standard`(用途：模型只说话不调工具时给递进提醒)在有文本且无 tool_calls 时返回 `HumanMessage`，见 `packages/graph-agent/src/graph_agent/core/nudge_injector.py:136-151`。

11. `build_standard_nudge_text`(用途：构造标准 nudge 文本)第一轮提示“输出了文本但未调用 finish_task”，第二轮警告必须调用工具或 finish_task，第三轮严重警告，见 `packages/graph-agent/src/graph_agent/cognitive/finish.py:118-134`。

12. `LLMPhaseNode` 旧路径曾有外层 nudge loop，`_run_cognitive_loop` 会在多次 `agent.invoke` 之间处理 finish gate、planning gate、checkpoint、standard nudge，见 `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py:284-333`；但当前 SDK V0.3.0 root live 走 `graph_assembler`。

13. 本地 LangChain `after_agent` hook 存在，见 `.venv/lib/python3.12/site-packages/langchain/agents/middleware/types.py:625-634`；`after_agent` decorator 支持 `can_jump_to`，见 `.venv/lib/python3.12/site-packages/langchain/agents/middleware/types.py:1437-1456`。

14. `create_agent` 会把最后一个 after_agent middleware 节点设为 `exit_node`，无 after_agent 时才把 `exit_node` 设为 END，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1433-1437`。

15. `create_agent` 把每个 after_agent middleware 装成独立节点 `{m.name}.after_agent`，after_agent 链注释明确“runs once at the very end, before END”，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1572-1595`。

16. LangGraph 的 `END` 常量就是 `__end__` 终端节点，见 `.venv/lib/python3.12/site-packages/langgraph/constants.py:28`。因此 `Command(goto=END)` 等价于直接跳到 `__end__`，不会先进入 `{m.name}.after_agent`。

17. `jump_to="end"` 与 `goto=END` 不同。LangChain `_resolve_jump` 会把 `jump_to="end"` 解析成 `end_destination`，而在有 after_agent 时 `end_destination` 是 after_agent 链尾节点，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1612-1624` 与 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1433-1437`。

18. deepagents `RubricMiddleware.after_agent` 参考范式说明 after_agent 是“Agent state at natural stop”，并可返回 `jump_to='model'`，见 `temp/deepagents/libs/deepagents/deepagents/middleware/rubric.py:425-441`、`temp/deepagents/libs/deepagents/deepagents/middleware/rubric.py:660-670`。

## Baseline / Alignment 差异

baseline 只有“finish_task 被调用后”的校验/接受/驳回；没有“模型不调用 finish_task 时”的结构性退出闸。alignment 目标是新增 after_agent 闸，集中控制唯一放行 END 的条件。

baseline 还暴露了一个 create_agent 迁移风险：CognitiveFlow 成功 finish_task 当前使用 `goto=END`，该跳转会直达 LangGraph 终端，绕过 after_agent 闸。alignment 必须把成功 finish_task 从“直接 END”改为“写 accepted marker，交给 after_agent 闸放行”。

## 决策原因

当前 `if not tool_calls: break` 是静默退出风险的直接证据，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:526-528`。只靠 prompt 或 NudgeInjector 的软提醒不能结构性保证 finish_task 出现。

NudgeInjector 可复用为消息生成器，但不能继续作为外层手写循环的唯一控制器；迁移到 create_agent 后，控制点应落到 after_agent，借 `jump_to:"model"` 阻止自然 END。

## 代码索引(clues)

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:526-528`: no tool_calls break。
- `packages/graph-agent/src/graph_agent/core/nudge_injector.py:136-151`: standard nudge 现成策略。
- `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1433-1437`: 有 after_agent 时的 exit_node。
- `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1572-1595`: after_agent 节点链位于 END 前。
- `.venv/lib/python3.12/site-packages/langgraph/constants.py:28`: END 是 `__end__` 终端。
- `temp/deepagents/libs/deepagents/deepagents/middleware/rubric.py:425-441`: after_agent 闸参考。

## 待办/疑点

1. 待办：新增 finish_task exit gate middleware，实现 `after_agent` + `jump_to:"model"`。
2. 待办：耗尽 max_iterations/recursion limit 时必须显式报错，不返回空 BusinessData。
3. 待办：CognitiveFlow 成功 finish_task 不得继续 `goto=END`；必须只标记 accepted，由 after_agent 退出闸统一放行。
