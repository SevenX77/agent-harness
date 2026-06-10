---
ws_id: WS-E5-checkpoint-inner
modules:
  - 02-mechanism/04-run-outer/03-checkpoint
  - 02-mechanism/05-run-inner/08-messages-state
  - 02-mechanism/04-run-outer/02-iterate
  - 02-mechanism/04-run-outer/01-graph-exec
  - 01-contract/04-data-contracts
depends_on:
  - WS-E1-step5-subgraph-io
blocks:
  - WS-E1-io
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e5-checkpoint-inner.md
  - packages/graph-agent/src/graph_agent/core/checkpointer.py
  - packages/graph-agent/src/graph_agent/core/state.py
  - packages/graph-agent/src/graph_agent/core/runner.py
  - packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py
spec_ssot:
  - docs/engine/mvp1/_impl/IMPL_PLAN.md
  - docs/engine/mvp1/_impl-backlog.md
  - docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md
  - docs/engine/mvp1/01-contract/04-data-contracts/mvp1-alignment.md
  - docs/development/task-spec-standard.md
status: drafted
created: 2026-06-09
baseline_head: 047d46f676ca2440ce4973ecb817c2dad7a83fa4
review_flow: requirements -> RED -> contract gate -> task + Gemini prompt -> Gemini GREEN -> Codex hard-exit review -> baseline writeback -> final review
---

# WS-E5 Checkpoint Inner - 需求书

> 本需求书是 WS-E5 的流水线输入。下一步只能写 RED 测试并跑到干净失败；未见 RED、未过契约门，不得写实施 task/Gemini prompt，不得实现生产代码。

## 1. 目标

把 checkpoint 从外层 run/thread 级推进到内层 AGENT loop 可寻址、可恢复的目标边界：AGENT 内层使用外层图的共享 base checkpointer，并用稳定 `checkpoint_ns` 区分外层图、agent 内层、iterate 轮次等执行层级。实现后，外层 blackboard state 与内层 messages/agent state 不能互相污染；同时要为后续 WS-E1-io 的 `StateManager.update_business`、artifact、`business_data_md` 链路留下正确状态边界，但本 WS 不实现文件 lazy 或 artifact。

## 2. SSOT 指针

- 实施计划：`docs/engine/mvp1/_impl/IMPL_PLAN.md` §二/§三/§六，WS-E5 依赖 WS-E1，阻塞 WS-E1-io。
- Backlog 来源：`docs/engine/mvp1/_impl-backlog.md` A3，目标是 AGENT 经稳定 namespace 挂外层共享 base checkpointer。
- checkpoint 目标唯一真理：`docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/mvp1-alignment.md` §1-§6/§8。注意：早期派单文字里的 `02-mechanism/03-checkpoint/mvp1-alignment.md` 在当前基线不存在，真实路径是 `04-run-outer/03-checkpoint`。
- 内层 messages 目标唯一真理：`docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/mvp1-alignment.md` §1-§6/§8。
- iterate namespace 背景：`docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/mvp1-alignment.md` §2/§5/§6。
- graph exec / IO 边界背景：`docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md` §2/§5，尤其文件 lazy / artifact 属 WS-E1-io，不属于本 WS。
- data-contracts 边界：`docs/engine/mvp1/01-contract/04-data-contracts/mvp1-alignment.md` §2/§5/§6，`BusinessData` 与 `FrameworkState` 是我们的状态形状，checkpoint 机制建在 LangGraph 原语上。
- 现状锚点：
  - `docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md`
  - `docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/baseline.md`
  - `docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md`
  - `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md`
- 流程标准：`docs/development/task-spec-standard.md` §一/§三/§四。
- 必读源码：
  - `packages/graph-agent/src/graph_agent/core/checkpointer.py`：共享 checkpointer 工厂、backend 选择、singleton reset。
  - `packages/graph-agent/src/graph_agent/core/state.py`：`WorkflowState`、`BusinessData`、`FrameworkState`、`StateManager.update_business` / `update_framework` / `route_finish_task`。
  - `packages/graph-agent/src/graph_agent/core/graph_assembler.py`：只作 grounding，重点读 `assemble_graph` 的 outer checkpointer 注入、AGENT create_agent 构造、现有 namespace wrapper、graph iterate config。若 RED 证明必须调整 AGENT invoke/config 接线，先停下请示是否扩 owns。
  - `packages/graph-agent/src/graph_agent/core/runner.py`：只在发现 run invoke/config 边界必须调整时触碰；否则只读核对 `thread_id` 与 checkpointer 进入 graph 的路径。
  - 既有回归测试：`packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py`、`packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py`、`packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py`、`packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py`。

基线说明：本任务接受 PR #118 head `047d46f676ca2440ce4973ecb817c2dad7a83fa4` 作为临时基线。PR #118 在开工核实时仍是 draft，py311/py312 checks pending；用户已确认继续。隔离 worktree 中相邻基线命令 `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py -q` 已通过 23 个测试。

## 3. 文件归属

本 WS owns 见 frontmatter `owns_files`。其中：

- `checkpointer.py` 是本 WS 首选生产落点，用于承载 GraphAgent 自己的 checkpointer helper/namespace 边界，而不是把 checkpoint 行为散在业务节点里。
- `state.py` 只允许处理外层 blackboard 与内层 messages/framework 的状态边界、business/framework 写入不污染的契约支撑；不得在本 WS 实现 blackboard data delta reducer 或 artifact 写入。
- `runner.py` 是条件 owns：只有 RED 证明 run invoke/config 边界无法在 checkpointer/state 层保真时才允许触碰。触碰前必须在契约门说明原因。
- `graph_assembler.py` 当前不在 owns。它是 WS-E1 热点文件；本 WS 只读核对。若发现 E1 create_agent checkpoint 接线缺口，或者 RED 只能通过改 AGENT invoke/config 解决，必须先停下请示，不得自行大改。

禁止触碰：

- `packages/graph-agent/src/graph_agent/middleware/tracing.py`、`tool_error.py`、`loop_detection.py`：归 WS-E2。
- `packages/graph-agent/src/graph_agent/middleware/nudge_injector.py`、exit-control 相关代码：归 WS-E8。
- `packages/graph-agent/src/graph_agent/io/**`、`packages/graph-agent/src/graph_agent/tools/builtin/read_file.py`、artifact/storage 相关代码：归 WS-E1-io。
- `packages/graph-agent/src/graph_agent/callbacks/events.py`、`packages/graph-agent/src/graph_agent/callbacks/emit.py`：本 WS 不做 callbacks/events/emit。
- `packages/graph-agent/src/graph_agent/core/loader.py` 的 subgraph IO 规则：WS-E1 Step5 已处理，本 WS 不重开。
- `apps/studio/**`、`packages/graph-agent-gateway/**`。

## 4. 现状锚点

baseline 文档仍把“内层 AGENT 挂 checkpoint”标为目标态；PR #118 代码已出现部分前进：AGENT create_agent 路径会接收外层 checkpointer，并有 namespace wrapper 与 `agent:<phase>` 风格的配置。既有 E1 测试只断言 create_agent 参数和配置里含有 agent/phase 语义，还不足以证明真实运行时写入了可区分的内层 checkpoint、历史读取能区分外层/内层、iterate 轮次 namespace 不会被 agent namespace 覆盖，或外层 blackboard 与内层 messages 不会互相污染。本 WS 的 RED 要补这些空白。

## 5. 目标行为

### 5.1 共享 base checkpointer

- 当外层 graph 以 checkpointer 编译并用某个 `thread_id` invoke 时，AGENT 内层 create_agent 必须使用同一个 base checkpointer，不得另起与外层不可互查的 saver。
- 内层 checkpointer 可以通过 GraphAgent helper 包装 namespace，但 history/get_state 的最终寻址必须仍落在同一 base、同一 thread 下面。
- 没有显式外层 checkpointer 的路径可以继续保持现有默认行为；本 WS 的核心验收是“有共享 base 时必须共享”。

### 5.2 稳定 namespace 分层

- 外层图 checkpoint、AGENT 内层 checkpoint、iterate 轮次 checkpoint 必须有稳定可区分的 namespace。namespace 的具体分隔符由实现者决定，但测试必须能证明它包含 scope 语义与必要实例标识，且不同层级不会同名碰撞。
- AGENT namespace 必须稳定包含 phase/agent 归属；两个不同 AGENT phase 不能写入同一内层 namespace。
- iterate namespace 必须稳定包含轮次归属；agent 运行在 iterate 内部时，不能用 agent namespace 覆盖或丢失当前 iterate 轮次归属。
- namespace 组合必须对 history/recovery 可用：外层查外层、内层查内层、某一轮查某一轮，不能靠扫描全部 checkpoint 后人工猜。

### 5.3 外层 blackboard 与内层 agent state 不互相污染

- 外层 `WorkflowState.data` 只承载用户业务黑板字段。AGENT 内层 messages、tool-call 中间消息、runtime/config/callback/compiled graph 等对象不得写入外层 business data。
- 内层 AGENT 可以读取当前 phase 需要的 state/input，但最终回到外层时，只能通过声明 output、finish_task 结果、`StateManager.update_business` / `update_framework` 这类边界写回。
- `BusinessData` 禁 `_` 前缀字段的约束不能被 checkpoint/resume 边界绕过；框架元数据必须留在 `FrameworkState`。
- 外层 `flow.thread_id` / `run_id` 等框架字段不得被内层 agent state 随意改写；若内层执行需要 config thread_id，应走 config，不污染 business data。

### 5.4 checkpoint 恢复与历史读取可区分

- 用共享 base 的 `list` / `get_tuple` / 等价 history API 读取同一 `thread_id` 时，必须能区分外层图 checkpoint 与 AGENT 内层 checkpoint。
- 读取 AGENT namespace 应看到内层 agent/messages 相关 state；读取外层 namespace 不应误拿到 agent 内层 state。
- 历史读取不要求本 WS 完整实现 Studio `resume_run` 或 HITL UI，但必须给后续 resume 链路留下可测试的寻址边界。

### 5.5 后续 business data / artifact 边界

- 本 WS 不实现文件 lazy、artifact、`business_data_md` 写盘，但要通过测试锁住边界：business 更新只能进入 `WorkflowState.data` 的用户字段，framework/meta 进入 `WorkflowState.flow`，messages 留在 messages 通道或内层 agent state。
- 后续 WS-E1-io 接 `StateManager.update_business` 与 artifact 时，不应需要从 agent checkpoint 里反向挖业务字段，也不应把 artifact/runtime 对象塞进 business data。

## 6. 测试要求

Codex 必须先写 RED，建议落点 `packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py`。RED 必须跑到干净失败，失败原因应落在 checkpoint namespace/history/state 边界，而不是夹具、依赖或旧测试环境问题。测试覆盖至少包括：

- 真实 AGENT create_agent 路径：使用共享 `InMemorySaver` 或等价 base checkpointer、真实 graph invoke、同一 `thread_id`，证明 AGENT 内层执行真实写入带 agent namespace 的 checkpoint。不得只 mock `create_agent` 参数到绿。
- 外层/内层不污染：运行后外层 `WorkflowState.data` 不包含 messages、tool-call、checkpoint config、runtime/callback/compiled graph 等内层对象；finish_task 或业务输出只通过 business 字段出现，framework/meta 留在 `flow`。
- iterate 与 agent namespace 不冲突：构造包含 iterate 轮次与 AGENT phase 的最小图，证明每轮 namespace 与 agent namespace 可组合、可区分，且 agent 执行不会覆盖 `iter{k}` 归属。
- history/recovery 可区分：同一 base、同一 `thread_id` 下，外层 checkpoint 与 agent 内层 checkpoint 可以通过 namespace 查询或等价 API 区分；读取外层不误取内层，读取内层不误取外层。
- business boundary 预留：覆盖 `StateManager.update_business` / `route_finish_task` 相关边界，证明 `_` 前缀框架字段不会进入 business data，后续 WS-E1-io 可以安全接 update_business/artifact 而不需要改变 checkpoint state 归属。
- 回归套件：保留 WS-E1 create_agent、LOGIC、iterate、subgraph IO 的关键测试不退化。最低验证命令应包含：
  - `uv run pytest packages/graph-agent/tests/core/test_ws_e5_checkpoint_inner_red.py -q`
  - `uv run pytest packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py -q`

## 7. 硬依赖约束

- 依赖 WS-E1 Step1-5 的 create_agent、logic、iterate、subgraph IO 基线。若 PR #118 后续 CI 失败，必须回头判断 WS-E5 RED 是否仍可作为可靠契约。
- 本 WS 先写 requirements，再写 RED，再停在契约门。RED 通过契约门后，才允许写 task + Gemini implementation prompt。
- 如果 RED 证明必须修改 `graph_assembler.py` 才能满足 AGENT checkpoint config/namespace，本 WS 必须先请示扩 owns；不能在 RED 阶段或实现阶段擅自大改热点文件。
- `runner.py` 只有在 run invoke/config 边界确实需要调整时才触碰；否则实现应收敛在 checkpointer/state 边界与测试。

## 8. 验收标准

- [ ] 当前 worktree/分支/HEAD/PR #118 基线状态已核实，并记录是否接受 pending CI 风险。
- [ ] requirements 已写完后才写 RED；契约门前不写 task/Gemini prompt。
- [ ] RED 测试先失败，失败原因干净落在内层 checkpoint namespace/history/state 边界。
- [ ] 契约门通过后，才允许写 task + Gemini prompt。
- [ ] 实现后 RED suite 变绿。
- [ ] WS-E1 create_agent、LOGIC、iterate、subgraph IO 回归套件保持绿。
- [ ] AGENT 内层使用共享 base checkpointer；同一 `thread_id` 下能区分外层与内层 checkpoint。
- [ ] iterate 轮次 namespace 与 agent namespace 不冲突，agent 内层不覆盖迭代归属。
- [ ] 外层 `WorkflowState.data` 与内层 messages/agent state 不互相污染。
- [ ] 未实现 WS-E1-io 文件 lazy/artifact/business_data_md，未实现 callbacks/events/emit，未触碰 Studio/gateway。
- [ ] 若最终需要改 `graph_assembler.py` 或非 owns 文件，已有明确 PM 扩 scope 记录。
- [ ] 实现落地后 baseline 按真实代码回写。

## 9. 不做

- 不改 middleware 后三槽，不实现 tracing/tool_error/loop_detection。
- 不改 exit/nudge，不实现 after_agent 退出闸。
- 不做 WS-E1-io 文件 lazy、artifact、`business_data_md`、`InputFileInjectedEvent`。
- 不做 callbacks/events/emit。
- 不做 Studio/gateway。
- 不做 blackboard data delta reducer、compact、有界 accumulator、durability 调参。
- 不做完整 Studio `resume_run` / HITL UI。只锁住后续 resume 所需的 checkpoint history/namespace 边界。
- 不把 `graph_assembler.py` 当作本 WS 默认生产落点；发现 create_agent checkpoint 接线缺口先请示。

## 10. baseline 回写指令

实现落地后按真实代码回写：

- `docs/engine/mvp1/02-mechanism/04-run-outer/03-checkpoint/baseline.md`：记录共享 base、内外 namespace、history/recovery 区分、仍未实现的 data delta/compact/durability。
- `docs/engine/mvp1/02-mechanism/05-run-inner/08-messages-state/baseline.md`：记录 AGENT 内层 messages 是否已经 namespace checkpoint，仍未实现的 summarization/HITL resume。
- `docs/engine/mvp1/02-mechanism/04-run-outer/02-iterate/baseline.md`：只记录 iterate namespace 与 checkpoint 交互真实状态，不提前写 trace/event。
- `docs/engine/mvp1/01-contract/04-data-contracts/baseline.md`：如 state helper 或 business/framework 边界有真实变更，照实回写；不提前写 artifact。
- `docs/engine/mvp1/_impl/IMPL_PLAN.md`：如 PM 要求维护进度面板，更新 WS-E5 状态。

## 11. 评审检查点

- 契约门：重点审 RED 是否真实覆盖共享 base、namespace 分层、history 区分、state 不污染、iterate/agent 不冲突；同时审是否越界到 E2/E8/E1-io/events/Studio/gateway。
- Codex 审查退出：只按 §8 硬退出条件，不接受“参数看起来传了”这种浅层证明；必须看真实 checkpoint 写入和 history 区分。
- Claude 终审：查实现是否合意图、baseline 是否诚实、测试是否只 mock 到绿、是否未经确认触碰 `graph_assembler.py` 或其它非 owns 文件。

## 12. 给 Codex 的交接

契约门通过后，Codex 据已批准 RED 写 `.kiro/specs/engine-mvp1/task-ws-e5-checkpoint-inner.md` 和 Gemini prompt，遵守：

- 来源 = 已批准测试，测试是契约；不凭空设计实现步骤。
- 格式 = Phase 分段 + `- [ ]` 勾选项 + 每条挂 `_Requirements: <模块.功能>` + 验证命令。
- frontmatter 指回本需求书和 `spec_ssot`，不重写设计。
- 嵌入编排注解：`owns_files`、实现者 = Gemini、§8 硬退出。
- 行号 Codex 落地时自己重新核；本需求书不把行号当编辑坐标。
- 不跑 `/kiro:spec-tasks`，避免 clobber。
- 同步输出 Gemini prompt，包含工作区路径、必读文件、RED 测试结果、owns_files/禁止触碰、目标行为、验证命令和回报格式。
- 完整规范见 `docs/development/task-spec-standard.md` §四 4.2。
