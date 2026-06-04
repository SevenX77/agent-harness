---
module: 02-finish-task-submission
doc: baseline
status: drafted
last_verified: 2026-06-02
---

# 02-finish-task-submission — Baseline(现状)

核心结论：finish_task 当前是模型显式调用的 LangChain `StructuredTool`。它的入参是最终 markdown 交付物；live loop 执行工具后把返回结果交给 CognitiveFlow 桥接处理。当前不是“loop 结束后从最后一条自然语言消息里抽取输出”的后置校验器。

## 覆盖范围

覆盖范围：本文覆盖决策记录 §4 对应的 finish_task 提交定位。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| `cognitive/finish_task.py:FinishTaskInput` | `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:21-24` | finish_task 工具入参 schema，核心字段是 `markdown`。 |
| `cognitive/finish_task.py:build_finish_task_tool` | `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:30-100` | 构造 `StructuredTool`，工具名为 `finish_task`。 |
| `graph_assembler.py:_build_agent_finish_task_tool` | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:636-647` | live agent phase 把 finish_task 加入工具列表。 |
| `graph_assembler.py:_skill_node` | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:529-572` | 模型 tool call 触发 tool.invoke，然后交给 CognitiveFlow 判断是否结束。 |
| `middleware/cognitive_flow.py:handle_finish_task_tool_result` | `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:198-269` | 当前手写 loop 的 finish_task 桥接处理。 |

## 编号执行流程(现状)

1. `FinishTaskInput`(用途：定义 finish_task 的 LangChain tool args)只有 `markdown: str` 字段，描述为当前 phase 的最终 markdown 输出，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:21-24`。

2. `build_finish_task_tool`(用途：构造 finish_task StructuredTool)接收 `output_schema`、`md2json` 转换器、可选 patcher 和最大 patch 次数，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:30-35`。

3. `_finish_task`(用途：StructuredTool 内部函数)先拒绝空 markdown；非空时调用 `md2json(markdown, output_schema)`，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:40-50`。

4. `_finish_task` 如果没有 validation errors，返回 `{"ok": True, "data": result.data, "repaired": result.repaired}`，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:49-51`。

5. `_finish_task` 如果有 validation errors 且 patcher 可用，会循环调用 patcher，再重新跑 md2json，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:52-93`。

6. `StructuredTool.from_function` 把 `_finish_task` 暴露为名为 `finish_task` 的工具，描述是提交 phase final output，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:95-99`。

7. `_build_agent_finish_task_tool`(用途：为 agent phase 构造 finish_task 工具)把 `parse_finish_markdown` 和 `LLMMdPatchClient` 接给 `build_finish_task_tool`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:636-647`。

8. `_build_skill_node` 把 finish_task 放进 `all_tools`，再让模型绑定这些工具，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:474-480`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:508`。

9. `_skill_node` 遍历模型返回的 `tool_calls`，按 name 找工具并执行，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:526-546`。

10. `_skill_node` 执行任意工具后都会追加 `ToolMessage`，再调用 `cognitive_flow.handle_finish_task_tool_result`；只有 tool name 是 finish_task 时该方法才处理，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:556-572` 与 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:198-210`。

11. `handle_finish_task_tool_result`(用途：手写 loop 下处理 finish_task 结果)把结果写入 `flow["finish_task_result"]`，如果 `ok` 不为真则把 flow/messages 返回给 loop，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:212-228`。

12. `handle_finish_task_tool_result` 在 `ok=True` 后继续做 schema gate，最终通过 `_finish_task_accept_response` 返回 phase state 更新，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:229-269`。

## Baseline / Alignment 差异

baseline 已经把 finish_task 作为显式提交工具接入模型工具列表。alignment 不改变这个定位；只改变它所在的 loop：从手写 tool-call 分发迁到 `create_agent` 的工具循环与 middleware。

## 决策原因

finish_task 不能降级为后置校验器，因为 graph-agent 的业务输出是给下游 phase 消费的结构化 BusinessData。当前代码也已经把结构化交付物放在 tool args 里，而不是放在模型最终自然语言消息里，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:21-24`。

保留显式提交工具可以消除“最后一条消息哪一段是交付物”的歧义。当前 `handle_finish_task_tool_result` 只响应名为 `finish_task` 的工具结果，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:198-210`。

## 代码索引(clues)

- `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:95-99`: finish_task 是 `StructuredTool`。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:474-480`: finish_task 被加入 agent tools。
- `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:198-269`: finish_task 结果桥接到 phase state。

## 待办/疑点

1. 待办：迁移到 create_agent 后继续把 finish_task 作为工具注册，并确保它不是普通后置文本抽取器。
2. 待办：明确 finish_task 是否设置 `return_direct`。当前目标倾向不使用 return_direct，让退出权集中到 after_agent 闸，详见 `../04-exit-control/mvp1-alignment.md`。
