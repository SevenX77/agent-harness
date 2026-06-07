---
module: 02-finish-task-submission
doc: mvp1-alignment
status: drafted
last_verified: 2026-06-02
---
<!-- 核对进度:已迁 7 块 / 未迁 0 块 / 2026-06-04 -->

~~# 02-finish-task-submission — MVP1 Alignment(目标设计)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

MVP1/V4 决策：finish_task 继续是模型显式调用的提交工具。模型必须用 tool call 把最终交付物作为参数提交；系统再对这份参数做 markdown 解析、schema 校验、业务校验和 exit gate 判断。

~~## 覆盖范围~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

覆盖范围：本文覆盖 finish_task 工具定位、create_agent 迁移后的注册方式、与 exit gate 的边界。

| 范围 | MVP1 目标 |
|---|---|
| `cognitive/finish_task.py:build_finish_task_tool` | 保留工具接口，不改为自然语言抽取。 |
| `middleware/cognitive_flow.py:wrap_tool_call` | 在 create_agent 工具循环中截获 finish_task。 |
| `04-exit-control` | after_agent 闸负责“能不能 END”，finish_task 负责“提交了什么”。 |

~~## 目标设计与编号流程~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

1. `finish_task` 注册为 create_agent 的普通工具之一。现状工具名和 args schema 已固定在 `StructuredTool.from_function`，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:95-99`。

2. 模型提交时必须发出 `finish_task(markdown=...)` tool call。当前 args schema 是 `markdown`，见 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:21-24`；后续若 V4 spec 改为 `reasoning/diagnostics_md/business_data_md` 三字段，应作为新 V4 spec 工作，而不是本轮修改 frozen V0.3.0 spec。

3. `CognitiveFlowMiddleware.wrap_tool_call` 是 create_agent 迁移后的截获点。它已经能识别 `finish_task`，在有 `WorkflowState` 时转入 `_handle_finish_task`，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:348-390`。

4. finish_task 工具本身不拥有“最终退出权”。它只提交和验证 payload；能否放行 `END` 交给 `after_agent` exit gate 统一判断，避免 return_direct 绕过集中闸。

5. 结构化输出仍从 finish_task 入参进入系统，不从末条 `AIMessage.content` 猜测。当前手写 loop 只在 tool call 分支调用 finish_task，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:529-572`。

6. 如果模型自然语言回答但不调用 finish_task，`after_agent` 闸应注入 nudge 并 `jump_to:"model"`，详见 `../04-exit-control/mvp1-alignment.md`。

~~## 已实现 / 与 baseline 差异~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

已实现：finish_task 的 `StructuredTool` 形态、显式 `markdown` 参数、md2json/patcher 调用骨架都在 `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:30-100`。

已实现：CognitiveFlow 已经有 `wrap_tool_call` 可作为 create_agent 迁移后的 tool-call 截获点，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:348-390`。

未实现：live loop 还没有走 create_agent 的工具节点；当前仍在 `_skill_node` 手动执行 `tool.invoke`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:529-546`。

~~## 决策原因~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

保持显式提交工具，是为了把业务交付物的边界变成模型行为里的显式信号。被否决的“loop 结束后抽取末条消息”会引入交付物边界歧义，且无法可靠区分解释文字、思考性总结和真正下游 BusinessData。

finish_task 不负责后置 END 放行，是为了化解 agent loop 架构和 finish_task 校验路由冲突。提交工具负责 payload；exit gate 负责 phase lifecycle；两者分开后，create_agent 无 tool_calls 的自然结束不会绕过校验。

~~## 代码索引(clues)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

- `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:21-24`: 提交入参是最终 markdown。
- `packages/graph-agent/src/graph_agent/cognitive/finish_task.py:95-99`: 工具名为 `finish_task`。
- `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:348-390`: create_agent 目标截获点。

~~## 待办/疑点~~ → ✅[已迁入](../../02-mechanism/05-run-inner/03-cognitive/mvp1-alignment.md#2-数据流--机制)

1. 待办：迁移测试要覆盖“模型只发自然语言、不调 finish_task”时不能通过 phase。
2. 待办：V4 spec 需要重新定义 finish_task 参数形状；本轮只标注需求，不修改 `docs/engine/mvp0/skill-spec`。

