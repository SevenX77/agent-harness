---
module: 05-subagent-dispatch
doc: baseline
status: drafted
last_verified: 2026-06-02
---
<!-- 核对进度:已迁 7 块 / 未迁 0 块 / 2026-06-04 -->

~~# 05-subagent-dispatch — Baseline(现状)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/baseline.md#后端功能)

核心结论：subagent 调度当前是手写 loop 里的特殊分支。`call_subagent_<name>` 工具名由编译结果生成，`_skill_node` 在普通工具执行前判断是否是 subagent，然后调用 `_invoke_subagent_tool_t21`。这套逻辑包含 depth guard、参数校验、子图 invoke、child config 和结果 delta；MVP1 应迁入 `wrap_tool_call` middleware。

~~## 覆盖范围~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/baseline.md#后端功能)

覆盖范围：本文覆盖决策记录 §7。

| 覆盖目标 | 现状范围 | 覆盖说明 |
|---|---|---|
| subagent 工具名映射 | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:692-699` | 生成 `call_subagent_<name>`。 |
| live 特判分支 | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:529-546` | 手写 loop 内判断 subagent。 |
| `_invoke_subagent_tool_t21` | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1057-1117` | depth、retry、schema validation、runtime invoke 入口。 |
| subagent runtime map | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1120-1155` | 预编译 child skill 并装配 child graph。 |
| child invoke / config | `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1158-1277` | 子图执行、结果 delta、run metadata。 |
| schema helper | `packages/graph-agent/src/graph_agent/core/subagents.py:92-157` | 参数校验和 depth guard。 |

~~## 编号执行流程(现状)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/baseline.md#后端功能)

1. `_subagent_tool_map`(用途：为一个 phase 的 subagents 生成工具名映射)把每个 subagent 映射成 `call_subagent_{subagent.name}`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:692-699`。

2. `_build_skill_node` 先构造 `subagent_by_tool_name`，再构造 `subagent_runtime_by_tool_name`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:455-465`。

3. `_subagent_runtime_map`(用途：预编译每个 subagent 对应 child graph)用 `_compilation_cache` 复用已编译 skill，再递归调用 `assemble_graph`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1120-1155`。

4. `_skill_node` 在每个 tool call 上取 name 和 args，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:529-534`。

5. 如果 tool name 命中 `subagent_by_tool_name`，`_skill_node` 调 `_invoke_subagent_tool_t21`，否则调普通 `tool.invoke`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:535-546`。

6. `_invoke_subagent_tool_t21`(用途：执行或校验 subagent 工具调用)先用 `assert_subagent_depth_allowed(current_subagent_depth(flow))` 做深度守卫，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1057-1070`。

7. `_invoke_subagent_tool_t21` 用 `flow["subagent_validation_retries"]` 记录当前工具的参数校验 retry 次数，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1071-1076`。

8. `_invoke_subagent_tool_t21` 调 `validate_subagent_tool_args` 校验 `{"inputs": [...]}`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1077-1085`。

9. `validate_subagent_tool_args`(用途：校验 call_subagent 工具 args)要求 `inputs` 是 list，并逐项用 Pydantic input model validate，见 `packages/graph-agent/src/graph_agent/core/subagents.py:92-147`。

10. 如果校验失败但未耗尽 retry，`SubagentValidationFailure.to_tool_result` 返回可给 LLM 的 tool result，见 `packages/graph-agent/src/graph_agent/core/subagents.py:15-34`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:1097-1098`。

11. 如果 runtime 存在，`_invoke_subagent_tool_t21` 调 `_invoke_subagent_many_t24` 并返回 `ok/results`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1099-1111`。

12. `_invoke_subagent_once_t23`(用途：执行一个 child input)构造 child `WorkflowState`，调用 child graph，再用 `_dict_delta` 返回 child 输出增量，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1158-1180`。

13. `_child_flow` 会把 parent flow dump 出来，并将 `subagent_depth` 加一，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1183-1189`。

14. `_invoke_subagent_many_t24` 用 asyncio semaphore 控制并发，默认 concurrency=3，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1192-1251`。

15. `_subagent_runnable_config`(用途：给 child run 加 metadata/tags/run_id)写入 `parent_run_id` 和 `subagent_depth`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1254-1277`。

16. `FrameworkState` 当前保存 `subagent_validation_retries` 和 `subagent_depth`，见 `packages/graph-agent/src/graph_agent/core/state.py:183-194`。

~~## Baseline / Alignment 差异~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/baseline.md#后端功能)

baseline 的 subagent 调度耦合在手写 `_skill_node` 里。alignment 目标是在 create_agent 工具执行链上用 `wrap_tool_call` 拦截 `call_subagent_*`，让 subagent 逻辑成为 middleware，而不是 loop 内特判。

~~## 决策原因~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/baseline.md#后端功能)

迁移到 create_agent 后，手写 `if name in subagent_by_tool_name` 分支会消失；如果不迁入 middleware，subagent 工具要么变成普通 LangChain tool，要么失去 depth、schema retry、child flow 和 run metadata。当前特殊逻辑证据在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:535-546`。

用 `wrap_tool_call` 是因为 LangChain tool call request 能访问 `request.state`，CognitiveFlow 已经用 `_workflow_state_or_none(request.state)` 证明可行，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:382-390`。

~~## 代码索引(clues)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/baseline.md#后端功能)

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:535-546`: subagent live 特判。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1057-1117`: subagent 调度核心。
- `packages/graph-agent/src/graph_agent/core/subagents.py:92-147`: subagent 参数校验。
- `packages/graph-agent/src/graph_agent/core/state.py:183-194`: subagent 状态字段。

~~## 待办/疑点~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/baseline.md#后端功能)

1. 待办：新增 SubagentDispatchMiddleware，实现 `wrap_tool_call` 拦截 `call_subagent_*`。
2. 待办：迁移测试要覆盖 depth guard、schema retry、child run metadata、并发结果顺序。
3. 疑点：subagent middleware 需要哪些 compile-time runtime map 依赖，应由 `_build_skill_node` 注入，还是挂在 middleware constructor。

