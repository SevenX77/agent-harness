---
ws_id: WS-E5-checkpoint-inner
artifact: gemini-prompt
status: ready-for-gemini
created: 2026-06-09
task_file: .kiro/specs/engine-mvp1/task-ws-e5-checkpoint-inner.md
requirements: .kiro/specs/engine-mvp1/requirements-ws-e5-checkpoint-inner.md
scope_expansion: "2026-06-09 PM/user allowed minimal core/graph_assembler.py changes for WS-E5 AGENT/iterate namespace wiring after the initial prompt gate."
---

# Gemini Prompt - WS-E5 Checkpoint Inner

```text
你是 /Users/sevenx/.config/superpowers/worktrees/agent-harness/codex-engine-mvp1-ws-e5-checkpoint-inner 工作区的 engine 模块实现者。请按 TDD 执行 WS-E5 checkpoint inner：RED 测试已由 Codex 写好，并已通过 PM/用户契约门审查。你的任务是只做最小 GREEN 实现。初始 prompt 要求如果实现需要触碰 graph_assembler.py 必须先停下；后续 PM/用户已明确扩 scope，允许为 WS-E5 AGENT/iterate namespace wiring 做最小 graph_assembler.py 修改。

工作区：
/Users/sevenx/.config/superpowers/worktrees/agent-harness/codex-engine-mvp1-ws-e5-checkpoint-inner

当前分支 / 基线：
codex/engine-mvp1-ws-e5-checkpoint-inner
HEAD: 047d46f676ca2440ce4973ecb817c2dad7a83fa4

基线说明：
PR #118 head 047d46f676ca2440ce4973ecb817c2dad7a83fa4 是本 WS 临时基线。契约门前 Codex 已核实 PR #118 为 open draft；部分 CI 当时 pending，按需求书接受 pending CI 风险继续。

任务书：
.kiro/specs/engine-mvp1/task-ws-e5-checkpoint-inner.md

需求书：
.kiro/specs/engine-mvp1/requirements-ws-e5-checkpoint-inner.md

铁律：
1. 已批准 RED 测试是实现契约；不要削弱测试来变绿。
2. task/prompt 只能基于已批准 RED，不新增未审契约。
3. 先跑 RED，看到它以同样形状失败，再写最小实现。
4. 只在 owns_files 内实现。若必须改 graph_assembler.py 或其它非 owns 文件，立即停下，报告需要扩 scope；不要先改了再解释。
5. 不实现 WS-E1-io 文件 lazy、artifact、business_data_md，不做 callbacks/events/emit，不做 middleware E2/E8，不做 Studio/gateway。

必须先读并回述关键现状：
- .kiro/specs/engine-mvp1/requirements-ws-e5-checkpoint-inner.md
  重点：目标行为、owns_files、禁止触碰、测试要求、硬退出、baseline 回写。
- .kiro/specs/engine-mvp1/task-ws-e5-checkpoint-inner.md
  重点：Phase 0 到 Phase 6、Scope Feasibility Gate、Hard Exit Checklist。
- docs/engine/mvp1/_impl/IMPL_PLAN.md
  重点：WS-E5 依赖 WS-E1，阻塞 WS-E1-io。
- docs/engine/mvp1/_impl-backlog.md
  重点：A3，AGENT 通过稳定 namespace 挂外层共享 base checkpointer。
- docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md
  重点：唯一 base + checkpoint_ns 嵌套；外层 blackboard 与内层 messages 分治。
- docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/mvp1-alignment.md
  重点：AGENT 内层 messages 经 namespace 挂共享 base；HITL/resume 后续边界。
- docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/mvp1-alignment.md
  重点：iterate namespace、图级/节点级 loop 与 checkpoint 的关系。
- docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md
  重点：AGENT 委派内层；WS-E1-io 文件 lazy/artifact 不属于本 WS。
- docs/engine/mvp1/01-contract/04-data-contracts/mvp1-alignment.md
  重点：BusinessData / FrameworkState / WorkflowState 分界。
- packages/graph-agent/src/graph_agent/core/checkpointer.py
  重点：共享 checkpointer 工厂、backend 选择、singleton reset。本 WS 首选生产落点。
- packages/graph-agent/src/graph_agent/core/state.py
  重点：BusinessData、FrameworkState、WorkflowState、StateManager.update_business / update_framework / route_finish_task。
- packages/graph-agent/src/graph_agent/core/runner.py
  只在 run invoke/config 边界确实需要时触碰。
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
  只读 grounding：assemble_graph 的 outer checkpointer 注入、AGENT create_agent 构造、现有 namespace wrapper、graph iterate config。禁止修改，除非 PM 扩 scope。

已批准 RED 测试：
packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py

先运行 RED：
uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py -q

当前预期 RED：
1 failed, 3 passed

失败形状必须保持干净：
- 唯一失败测试是 test_agent_inside_graph_iterate_preserves_iteration_namespace。
- saver.list 同一 thread_id 下可以看到外层 "" checkpoint，也可以看到 agent:main checkpoint。
- 失败原因是 agent 在 graph iterate 内部运行时丢失 iter1/iter2 归属，没有任何 namespace 同时包含 iter{k} 和 agent。
- 不是夹具错误、模型错误、compile 错误、business data 解析错误。

再运行回归基线：
uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q

当前预期：
36 passed

允许修改：
- packages/graph-agent/src/graph_agent/core/checkpointer.py
- packages/graph-agent/src/graph_agent/core/state.py
- packages/graph-agent/src/graph_agent/core/runner.py
- packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py 只允许修夹具错误，不允许削弱契约
- .kiro/specs/engine-mvp1/requirements-ws-e5-checkpoint-inner.md
- .kiro/specs/engine-mvp1/task-ws-e5-checkpoint-inner.md
- .kiro/specs/engine-mvp1/gemini-prompt-ws-e5-checkpoint-inner.md

禁止修改：
- packages/graph-agent/src/graph_agent/core/graph_assembler.py
- packages/graph-agent/src/graph_agent/middleware/tracing.py
- packages/graph-agent/src/graph_agent/middleware/tool_error.py
- packages/graph-agent/src/graph_agent/middleware/loop_detection.py
- packages/graph-agent/src/graph_agent/middleware/nudge_injector.py
- packages/graph-agent/src/graph_agent/io/**
- packages/graph-agent/src/graph_agent/tools/builtin/read_file.py
- packages/graph-agent/src/graph_agent/callbacks/events.py
- packages/graph-agent/src/graph_agent/callbacks/emit.py
- packages/graph-agent/src/graph_agent/core/loader.py
- apps/studio/**
- packages/graph-agent-gateway/**

目标行为：
1. 外层 graph 以 checkpointer 编译并用某个 thread_id invoke 时，AGENT 内层使用同一个 base checkpointer。
2. 同一 base、同一 thread_id 下，外层 checkpoint 与 AGENT 内层 checkpoint 可通过 checkpoint_ns 或等价 history API 区分。
3. 外层图 namespace 保持可查询，不被 AGENT 内层覆盖。
4. AGENT namespace 稳定包含 agent/phase 归属。
5. graph iterate 内部运行 AGENT 时，AGENT checkpoint namespace 同时保留 iter{k} 和 agent/phase 归属；agent namespace 不能覆盖或丢失 iter{k}。
6. 外层 WorkflowState.data 不含 messages、tool_calls、checkpoint config、runtime、callbacks、compiled_graph 或 _ 前缀框架字段。
7. StateManager.update_business 继续拒绝 _ 前缀字段；StateManager.route_finish_task 继续把 _ 元数据放进 flow.finish_task_result。
8. 不实现文件 lazy、artifact、business_data_md、callbacks/events/emit、Studio resume/HITL UI。

实现边界：
- 优先在 core/checkpointer.py 放 GraphAgent-owned namespace/checkpointer helper。
- state.py 只处理 business/framework 边界，不要把 checkpoint 行为塞进 business data。
- runner.py 只有 run invoke/config 边界确实需要时才触碰。
- graph_assembler.py 是当前热点文件且不在 owns。你可以读它定位现状；如果最终需要改 AGENT invoke/config 或 local NamespaceCheckpointer call site，必须停下请示扩 scope。
- 不要写未被 live 路径使用的“摆设 helper”来假装满足 owns；测试必须真实变绿。

执行顺序：
1. 读任务书、需求书、SSOT、源码，回述关键现状和你判断的最小落点。
2. 运行 approved RED 命令，确认仍是 1 failed, 3 passed 且失败形状如上。
3. 运行 WS-E1 回归命令，确认基线仍绿。
4. 做 Scope Feasibility Gate：
   - 如果仅改 checkpointer.py/state.py/runner.py 能让 approved RED 真实变绿，继续最小实现。
   - 如果必须改 graph_assembler.py，立即停下并回报：“WS-E5 GREEN requires scope expansion for graph_assembler.py”，附失败测试和具体需要改的调用边界，不要修改 forbidden file。
5. 若 scope 允许，最小实现共享 base / namespace helper。
6. 跑 targeted history/shared-base：
   uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py::test_agent_inner_checkpoint_writes_to_shared_thread_and_namespace packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py::test_history_queries_distinguish_outer_and_agent_checkpoints -q
7. 跑 targeted iterate+agent：
   uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py::test_agent_inside_graph_iterate_preserves_iteration_namespace -q
8. 跑 targeted state boundary：
   uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py::test_agent_inner_checkpoint_writes_to_shared_thread_and_namespace packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py::test_finish_task_framework_meta_stays_out_of_business_data -q
9. 跑完整 WS-E5：
   uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py -q
10. 跑完整回归：
   uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q
11. 跑 scope / hygiene：
   git diff -- packages/graph-agent/src/graph_agent/core/graph_assembler.py packages/graph-agent/src/graph_agent/middleware/tracing.py packages/graph-agent/src/graph_agent/middleware/tool_error.py packages/graph-agent/src/graph_agent/middleware/loop_detection.py packages/graph-agent/src/graph_agent/middleware/nudge_injector.py packages/graph-agent/src/graph_agent/io packages/graph-agent/src/graph_agent/tools/builtin/read_file.py packages/graph-agent/src/graph_agent/callbacks/events.py packages/graph-agent/src/graph_agent/callbacks/emit.py packages/graph-agent/src/graph_agent/core/loader.py apps/studio packages/graph-agent-gateway
   git status --short -- uv.lock
   git diff --check -- .kiro/specs/engine-mvp1/requirements-ws-e5-checkpoint-inner.md .kiro/specs/engine-mvp1/task-ws-e5-checkpoint-inner.md .kiro/specs/engine-mvp1/gemini-prompt-ws-e5-checkpoint-inner.md packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py packages/graph-agent/src/graph_agent/core/checkpointer.py packages/graph-agent/src/graph_agent/core/state.py packages/graph-agent/src/graph_agent/core/runner.py

uv.lock 注意：
- uv run 可能摸脏 uv.lock。
- 本 WS 没有依赖变更；如果 uv.lock 被摸脏，恢复它。

不要更新 baseline，除非用户/PM 明确要求。GREEN 后只报告真实落地行为，交给 Codex/PM 回写：
- docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md
- docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/baseline.md
- docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md
- docs/engine/mvp1/01-contract/04-data-contracts/baseline.md
- docs/engine/mvp1/_impl/IMPL_PLAN.md 如 PM 要求维护进度面板

回报格式：
1. 修改了哪些文件。
2. 每条验证命令的结果摘要。
3. 是否完全留在 owns_files；如果没有，给出 PM 扩 scope 的明确记录。
4. 最终 checkpoint 行为：共享 base、namespace 形状、history 查询行为、iterate+agent 组合行为。
5. 最终 state boundary 行为：business data 与 framework/agent state 如何分离。
6. 明确说明 forbidden engine files、apps/studio/**、packages/graph-agent-gateway/**、uv.lock 是否无未经授权 diff。
7. baseline 是否留给 Codex/PM 回写。
8. 若 hard-exit 未满足，说明原因并停下，不要扩大范围。
```
