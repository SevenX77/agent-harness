---
module: 05-subagent-dispatch
doc: mvp1-alignment
status: drafted
last_verified: 2026-06-02
---
<!-- 核对进度:已迁 7 块 / 未迁 0 块 / 2026-06-04 -->

~~# 05-subagent-dispatch — MVP1 Alignment(目标设计)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/mvp1-alignment.md#2-数据流--机制)

MVP1/V4 决策：把 `_invoke_subagent_tool_t21` 这套调度逻辑迁入 `wrap_tool_call` middleware。create_agent 负责工具循环，SubagentDispatchMiddleware 负责识别 `call_subagent_*`、校验参数、执行 child graph、维护深度和 trace metadata。

~~## 覆盖范围~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/mvp1-alignment.md#2-数据流--机制)

覆盖范围：本文覆盖 subagent 调度迁移目标、state/flow 读取方式和 deepagents 参考边界。

| 范围 | MVP1 目标 |
|---|---|
| `_subagent_tool_map` | 保留工具名约定。 |
| `_subagent_runtime_map` | 保留 child graph 预编译与 cache。 |
| `_invoke_subagent_tool_t21` | 迁入 middleware 的 handler 逻辑。 |
| `CognitiveFlowMiddleware.wrap_tool_call` | 作为 request.state 读取方式参考。 |
| deepagents `SubAgentMiddleware` | 只借鉴“middleware 托底 subagent tool”的模式，不照搬 task 工具接口。 |

~~## 目标设计与编号流程~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/mvp1-alignment.md#2-数据流--机制)

1. `_build_skill_node` 继续在 compile/runtime 准备阶段生成 `subagent_by_tool_name` 和 `subagent_runtime_by_tool_name`，现状位置见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:455-465`。

2. 新 `SubagentDispatchMiddleware` 构造时接收 `subagent_by_tool_name`、`subagent_runtime_by_tool_name`、callbacks、phase_name 等依赖，避免在 middleware 内重新编译 child skill。

3. `wrap_tool_call` 读取 `request.tool_call["name"]`。如果不是 `call_subagent_*`，直接调用 handler 透传；CognitiveFlow 对非 cognitive tools 的透传模式见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:353-363`。

4. 如果命中 subagent tool，middleware 从 `request.state` 取 `WorkflowState`，与 CognitiveFlow 的 `_workflow_state_or_none(request.state)` 模式一致，见 `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:382-390`。

5. middleware 调用现有 `_invoke_subagent_tool_t21` 等价逻辑，先做 depth guard。当前 depth guard 在 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1067-1070`，底层函数在 `packages/graph-agent/src/graph_agent/core/subagents.py:150-157`。

6. middleware 继续维护 `subagent_validation_retries`，见当前 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1071-1076` 与 `packages/graph-agent/src/graph_agent/core/state.py:183`。

7. 参数校验失败时返回 error tool result / ToolMessage 给主 agent，而不是抛出 phase fatal。当前 `SubagentValidationFailure.to_tool_result` 已提供可读 payload，见 `packages/graph-agent/src/graph_agent/core/subagents.py:24-34`。

8. 校验通过时调用 child graph。当前 `_invoke_subagent_once_t23` 会用 child input 构造 `BusinessData`，继承 child flow，并用 `_dict_delta` 只返回新增/变化数据，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1158-1180`。

9. child runnable config 保留 `parent_run_id`、`subagent_depth`、`tags=["subagent", subagent_name]`，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1254-1277`。

10. deepagents `SubAgent` 参考表明 subagent 可以作为 middleware 提供的 tool 暴露给主 agent，见 `temp/deepagents/libs/deepagents/deepagents/middleware/subagents.py:27-69`；但 engine 不照搬它的通用 `task` 工具接口，因为现有 V0.3.0 subagent tool 名和 input schema 已由 skill 编译产出。

~~## 已实现 / 与 baseline 差异~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/mvp1-alignment.md#2-数据流--机制)

已实现：所有 subagent 调度所需 helper 已存在，包含工具名映射、runtime map、校验、depth、child config 和并发执行，见 `packages/graph-agent/src/graph_agent/core/graph_assembler.py:692-699`、`packages/graph-agent/src/graph_agent/core/graph_assembler.py:1057-1277`。

未实现：这些 helper 仍由手写 loop 特判调用，没有作为 create_agent middleware 挂载。

~~## 决策原因~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/mvp1-alignment.md#2-数据流--机制)

迁入 middleware 是为了化解 subagent 隔离冲突。subagent 是 engine runtime 的隔离执行，不是普通业务工具；它必须保留 depth、child flow、parent metadata 和参数 retry。让它混进普通 ToolNode 会丢这些保护。

不照搬 deepagents `task` 工具，是因为 engine 的 subagent 是 skill-spec 声明产物，工具名和 schema 已经稳定为 `call_subagent_<name>`；改名为 `task` 会牵动 frozen V0.3.0 spec。

~~## 代码索引(clues)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/mvp1-alignment.md#2-数据流--机制)

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:692-699`: subagent tool naming。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1120-1155`: subagent runtime map。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:1254-1277`: child runnable config。
- `temp/deepagents/libs/deepagents/deepagents/middleware/subagents.py:27-69`: middleware 提供 subagent tool 的参考范式。

~~## 待办/疑点~~ → ✅[已迁入](../../02-mechanism/05-run-inner/07-subagent/mvp1-alignment.md#2-数据流--机制)

1. 待办：实现 SubagentDispatchMiddleware 前写 failing tests，证明 create_agent 路径下 subagent 仍走 engine dispatcher。
2. 待办：subagent 事件补 trace，至少包括 enter/exit/failure 和 child run id。
3. 疑点：child graph 是否应共享 parent checkpointer，还是用独立 thread_id；这与 `records/uncovered-areas.md` 的 checkpointer 项有关。

