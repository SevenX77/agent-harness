---
module: 04-exit-control
doc: mvp1-alignment
status: drafted
last_verified: 2026-06-02
---

# 04-exit-control — MVP1 Alignment(目标设计)

MVP1/V4 决策：退出权集中到一个 `after_agent` 闸。phase 只有在记录到合格 finish_task 后才能 END；模型无 tool_calls 想自然结束时，闸注入 nudge 并 `jump_to:"model"`；耗尽预算时显式失败，不静默返回空或坏 BusinessData。

## 覆盖范围

覆盖范围：本文覆盖 after_agent 闸、NudgeInjector、deepagents RubricMiddleware 范式、create_agent jump 能力。

| 范围 | MVP1 目标 |
|---|---|
| `CognitiveFlowMiddleware` | 负责校验并标记 finish_task accepted，不独占最终退出权。 |
| 新 exit gate middleware | 在 `after_agent` 判断是否允许 END。 |
| `NudgeInjector` | 复用 standard/selfcheck nudge 文本与计数策略。 |
| `ExecutionControlMiddleware` | 与 max_iterations / loop detection 协同，不重复做 END 放行。 |

## 目标设计与编号流程

1. 新增 exit gate middleware，hook 为 `after_agent`。本地 LangChain `after_agent` 返回 state update，并支持 decorator 的 `can_jump_to`，见 `.venv/lib/python3.12/site-packages/langchain/agents/middleware/types.py:625-634`、`.venv/lib/python3.12/site-packages/langchain/agents/middleware/types.py:1437-1456`。

2. exit gate 读取 state/flow 中是否已有合格 finish_task。当前 `FrameworkState.finish_task_result` 是 finish_task 中转字段，见 `packages/graph-agent/src/graph_agent/core/state.py:165-167`。

3. 如果 finish_task 已通过 schema/业务校验，exit gate 放行 END。CognitiveFlow 当前接受 finish_task 时会把 `finish_task_result` 写入 FrameworkState，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:479-492`。

4. 如果 agent 自然停止但没有合格 finish_task，exit gate 用 NudgeInjector 构造标准提醒。`try_standard` 已能在文本输出且无 tool_calls 时产生递进 `HumanMessage`，见 `packages/graph-agent/src/graph_agent/core/nudge_injector.py:136-151`。

5. exit gate 返回 `{"messages": [nudge], "jump_to": "model"}`，强制回到 model。deepagents `RubricMiddleware` 已用同构方式把 revision prompt 注入后 jump 回 model，见 `temp/deepagents/libs/deepagents/deepagents/middleware/rubric.py:660-670`。

6. 如果多次 nudge 后仍没有合格 finish_task，exit gate 不再返回自然 END，而是写入明确错误状态或抛 graph-agent fatal error。deepagents RubricMiddleware 在 max_iterations 耗尽时会标记 `max_iterations_reached` 并 warning，见 `temp/deepagents/libs/deepagents/deepagents/middleware/rubric.py:647-658`；engine 目标比它更硬：phase 失败要显式。

7. finish_task 倾向不设置 return_direct。LangChain 工具节点会在所有 client-side tool calls 都 return_direct 时走 end destination，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1750-1758`。MVP1 为了集中退出权，应避免 finish_task return_direct 绕过 exit gate。

8. `CognitiveFlowMiddleware._handle_finish_task` 当前返回 `Command(..., goto=END)`，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:499-512`。MVP1 决策：成功 finish_task 不得再 `goto=END`；CognitiveFlow 只写 `finish_task_accepted` / `finish_task_result` marker 与 ToolMessage，由 after_agent 退出闸读取 marker 后放行。

9. `goto=END` 会绕过 after_agent 闸。`create_agent` 有 after_agent 时把 `exit_node` 设为 `{last_after_agent}.after_agent`，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1433-1437`；after_agent 链作为独立节点运行在 END 前，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1572-1595`。

10. LangGraph `END` 是 `__end__` 终端，见 `.venv/lib/python3.12/site-packages/langgraph/constants.py:28`；CognitiveFlow 导入的是这个 END，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:31`，并在成功 finish_task 路径 `goto=END`，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:511`。因此该路径会直达终端，不会经过 `{m.name}.after_agent` 节点。

11. `jump_to="end"` 不是 `goto=END`。LangChain `_resolve_jump` 会把 `jump_to="end"` 解析为 `end_destination`，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1612-1624`；有 after_agent 时 `end_destination` 是 exit_node，也就是 after_agent 链尾，见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1433-1437`。反向也成立：after_agent 支持 `jump_to="model"` 回灌 loop，`model_destination=loop_entry_node` 见 `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1578-1595`。

12. `ExecutionControlMiddleware` 继续负责 iteration event、dead-end、轻量 loop；它不承担“是否完成”的业务放行，见 `packages/graph-agent/src/graph_agent/middleware/execution_control.py:67-90`。

13. 诚实边界：系统不能保证 LLM 一定会把任务做好；能保证的是 phase 不会静默成功。结果要么是合格 finish_task，要么是带错误码的显式失败。

## 已实现 / 与 baseline 差异

已实现：NudgeInjector 的 standard/selfcheck/planning 逻辑和 callback 计数已存在，见 `packages/graph-agent/src/graph_agent/core/nudge_injector.py:75-151`。

已实现：CognitiveFlow 已能驳回无效 finish_task 并 `goto="model"`，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:680-699`。

已实证：CognitiveFlow 当前成功路径 `goto=END` 会绕过 after_agent 退出闸；MVP1 必须改成 marker + exit gate 放行，而不是保留直接 END。

未实现：live path 没有 after_agent exit gate；手写 loop 的自然停止是 `break`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:526-528`。

## 决策原因

采用 after_agent，是因为 create_agent 默认自然停止发生在 agent 没有下一步 tool calls 时；这正是 `after_agent` 的语义位置。deepagents RubricMiddleware 的 docstring 也把它描述为 natural stop 处的状态，见 `temp/deepagents/libs/deepagents/deepagents/middleware/rubric.py:431-440`。

不靠 prompt 反复强调 finish_task，是因为结构性控制应该在 runtime，而不是把“必须提交”完全交给模型遵守。prompt 只定义一次提交格式，详见 `../08-prompt-and-cleanup/mvp1-alignment.md`。

耗尽显式失败，是为了化解错误码冲突：静默 END 会让下游看见缺失/空 BusinessData，却不知道是模型没提交、schema fail 还是 loop 预算耗尽。MVP1 应给这些分支结构化错误。

成功 finish_task 不再 `goto=END`，是为了让唯一退出权落在 after_agent 闸。否则模型一旦调用合格 finish_task，CognitiveFlow 会直接跳到 `__end__`，绕开用于防静默退出和预算耗尽报错的统一闸门。

## 代码索引(clues)

- `.venv/lib/python3.12/site-packages/langchain/agents/middleware/types.py:1437-1456`: after_agent 支持 `can_jump_to`。
- `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1433-1437`: 有 after_agent 时 exit_node 指向 after_agent 节点。
- `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1572-1595`: after_agent 节点链位于 END 前，且支持回 model。
- `.venv/lib/python3.12/site-packages/langchain/agents/factory.py:1612-1624`: `jump_to` 到 `model` / `end` 的解析。
- `.venv/lib/python3.12/site-packages/langgraph/constants.py:28`: END 是 `__end__`。
- `packages/graph-agent/src/graph_agent/core/state.py:165-167`: finish_task_result 状态字段。
- `packages/graph-agent/src/graph_agent/core/nudge_injector.py:136-151`: standard nudge。
- `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:680-699`: invalid finish_task 回 model 的现有模式。

## 待办/疑点

1. 待办：新增 exit gate 的 failing tests：无 tool_calls 不得 END、合格 finish_task 才 END、预算耗尽显式失败。
2. 待办：D-test-2 覆盖 after_agent `jump_to:"model"` 重入端到端，证明无 finish_task 的自然停止会被 nudge 回模型，并最终合格提交或显式失败。
3. 待办：CognitiveFlow 成功 finish_task 路径改成 accepted marker，不再 `goto=END`。
4. 待办：为“耗尽未提交 finish_task”定义 V4 错误码；本轮文档只标注，不改 frozen error-code spec。
