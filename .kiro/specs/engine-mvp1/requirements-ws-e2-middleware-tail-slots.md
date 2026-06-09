---
ws_id: WS-E2-middleware-tail-slots
modules:
  - 02-mechanism/05-run-inner/02-middleware
  - 02-mechanism/05-run-inner/04-tools
  - 02-mechanism/06-seam/02-observability
depends_on:
  - WS-E1
blocks:
  - WS-E1-io
owns_files:
  - .kiro/specs/engine-mvp1/requirements-ws-e2-middleware-tail-slots.md
  - packages/graph-agent/src/graph_agent/middleware/tracing.py
  - packages/graph-agent/src/graph_agent/middleware/tool_error.py
  - packages/graph-agent/src/graph_agent/middleware/loop_detection.py
  - packages/graph-agent/src/graph_agent/middleware/factory.py
  - packages/graph-agent/tests/middleware/test_ws_e2_middleware_tail_slots_red.py
spec_ssot:
  - docs/engine/mvp1/_impl/IMPL_PLAN.md
  - docs/engine/mvp1/_impl-backlog.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/baseline.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/baseline.md
  - docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md
  - docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md
status: drafted
created: 2026-06-09
related_pr: https://github.com/SevenX77/agent-harness/pull/118
review_flow: PM 写需求书 -> Codex 写 RED 测试 -> PM 契约门 -> Codex 写 task.md + Gemini prompt -> Gemini 实现 GREEN -> Codex 审 -> Codex 回写 baseline -> PM 终审
---

# WS-E2 Middleware Tail Slots 需求书

> 本需求书覆盖 Engine MVP1 的 WS-E2：把已经接入 AGENT 的 6 槽 middleware 后三槽从 no-op 变成 MVP1 契约行为。下一步是 Codex 按 §6 写失败测试；未见 RED、未过契约门，不得写 implementation task、Gemini prompt 或生产实现。

## 1. 目标

实现 middleware 后三槽的最小 MVP1 行为：Tracing 保留 agent 内 phase/tool/agent 上下文并接入现有 callback trace 面，ToolError 把工具异常转成 error ToolMessage 喂回 LLM 而不是让 phase 直接崩，LoopDetection 识别重复无进展循环并给出中断/诊断信号。WS-E1 已把 6 槽链接进 live AGENT，本 WS 负责后三槽不再只是空壳。

## 2. SSOT 指针

- 整体计划：`docs/engine/mvp1/_impl/IMPL_PLAN.md` §二/§三/§六，WS-E2 依赖 WS-E1，owns middleware 后三槽。
- Backlog 来源：`docs/engine/mvp1/_impl-backlog.md` Tier 1 A1/A2。
- middleware 目标唯一真理：`docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/mvp1-alignment.md` §2/§5/§6/§8。
- middleware 现状锚点：`docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/baseline.md` 后端功能 §1-§3 和差异表。
- ToolError 目标唯一真理：`docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/mvp1-alignment.md` §2/§6/§8。
- ToolError 现状锚点：`docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/baseline.md` §3 与差异表。
- Tracing 目标唯一真理：`docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md` §2/§6/§8。
- Tracing 现状锚点：`docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md` 后端功能 §2/§4 与差异表。
- 必读源码：
  - `packages/graph-agent/src/graph_agent/middleware/factory.py` 的 `build_middleware_chain`。
  - `packages/graph-agent/src/graph_agent/middleware/tracing.py`。
  - `packages/graph-agent/src/graph_agent/middleware/tool_error.py`.
  - `packages/graph-agent/src/graph_agent/middleware/loop_detection.py`.
  - `packages/graph-agent/src/graph_agent/middleware/execution_control.py` 的 dead-end 与轻量 loop 行为，只作边界 grounding。
  - `packages/graph-agent/src/graph_agent/callbacks/base.py` 与 `callbacks/events.py` 的既有 callback/typed event surface，只读使用。
  - `packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py` 的 create_agent/middleware live 回归。

## 3. 文件归属

本 WS owns 见 frontmatter `owns_files`。

`factory.py` 只允许在确需把 callbacks 或配置传给后三槽时触碰；不得重排 6 槽顺序，不得改变前三槽构造契约。

禁止触碰：

- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`。若 RED 证明 WS-E1 接线缺口，必须停下请示，不得直接修。
- `packages/graph-agent/src/graph_agent/core/checkpointer.py`、`core/state.py`，归 WS-E5。
- `packages/graph-agent/src/graph_agent/middleware/nudge_injector.py` 或 exit/nudge 相关新槽，归 WS-E8。
- `packages/graph-agent/src/graph_agent/callbacks/events.py`、`callbacks/emit.py`、`callbacks/base.py`，V4 事件 schema/emit 归 WS-E4。
- `packages/graph-agent/src/graph_agent/tools/builtin/read_file.py`、`packages/graph-agent/src/graph_agent/io/**`、`packages/graph-agent/src/graph_agent/core/runner.py` 的文件 lazy/artifact 相关逻辑，归 WS-E1-io。
- `apps/studio/**`、`packages/graph-agent-gateway/**`、`uv.lock`。

共享文件协调：

- WS-E4 已补 V4 trace schema，但本 WS 不 owns schema 文件。Tracing 只能消费已有 callback/event surface；如果需要新增字段或事件类，必须停下拆回 WS-E4。
- LoopDetection 必须复核 ExecutionControl 的现有 dead-end/轻量 loop，避免重复注入同类提示。ExecutionControl 可读不可改。

## 4. 现状锚点

WS-E1 head 上 `build_middleware_chain` 已按契约顺序构造 6 槽，并且 `graph_assembler._build_skill_node` 已把该链传给 `create_agent`。但后三槽 `TracingMiddleware`、`ToolErrorHandlingMiddleware`、`LoopDetectionMiddleware` 仍只保存 `phase_name`，没有 hook 行为；ToolError、Tracing、LoopDetection 的 MVP1 职责仍未落地。

## 5. 目标行为

### 5.1 6 槽链与顺序

- `build_middleware_chain` 必须继续返回 6 槽，顺序严格为 `ProtocolValidation -> CognitiveFlow -> ExecutionControl -> Tracing -> ToolError -> LoopDetection`。
- 后三槽必须是真实 hook 参与者，不得只靠类存在或构造成功假装完成。
- 不得让后三槽削弱前三槽的 ProtocolValidation、CognitiveFlow、ExecutionControl 行为。

### 5.2 ToolError

- 普通工具执行抛出异常时，ToolError 槽必须把异常转换成 `ToolMessage(status="error")`，并把它喂回 LLM 所在 message stream。
- error ToolMessage 必须保留可诊断上下文：至少能看出 phase、tool name、tool_call_id 和异常摘要。
- ToolError 不处理 LangGraph interrupt/HITL/GraphBubbleUp 类控制流；这类中断不得被误包成普通工具错误。
- ToolError 不新增错误码、不改 Error V2 registry、不改变 builtin 工具 schema。

### 5.3 LoopDetection

- LoopDetection 必须识别重复无进展循环，尤其是同一 tool/signature 连续或窗口内反复出现且没有新的有效进展时。
- 命中阈值时必须产生中断或明确诊断信号，不能静默 `None` 后让 loop 继续无限跑。
- LoopDetection 与 ExecutionControl 分工必须清楚：ExecutionControl 现有 dead-end warning 和轻量 callback 不应被删除或重复实现；LoopDetection 负责更硬的 loop 保护。
- LoopDetection 不实现 exit gate、不写 finish_task marker、不做 nudge 注入。

### 5.4 Tracing

- Tracing 必须在 middleware hook 层保留关键上下文：phase、tool、agent 内父节点关系，以及工具调用结果摘要。
- Tracing 必须接入现有 callback/trace 行为，至少不让迁到 create_agent 后的 tool/LLM 可观测覆盖低于现状。
- Tracing 不声明 WS-E4 的 V4 schema 或真实 emit 点已经完成；`parent_node_id`/`node_type` 只能在已有事件字段允许时使用。
- Tracing 不改 predict usage 归零策略，不改 `PredictTracingCallback`。

### 5.5 回归

- WS-E1 的 create_agent、finish_task、subagent dispatch、logic runtime、iterate runtime、subgraph IO 放宽不得退化。
- 本 WS 不解决 PR #118 的 pending CI；只基于其 head 做隔离增量。

## 6. 测试要求

Codex 必须先写 RED 测试，并在当前 baseline 下跑到干净失败。测试应覆盖：

- ToolError：构造一个真实 `ToolCallRequest`，handler 抛普通异常，断言返回 error `ToolMessage` 而不是异常外冒；断言 message 保留 phase/tool/tool_call_id/异常摘要。
- ToolError 控制流边界：interrupt/GraphBubbleUp 类控制流不得被普通 ToolError 吞掉；若当前环境难以直接构造该类型，需求测试可只锁普通异常路径，并在契约门记录 deferred 边界。
- LoopDetection：构造重复同一 tool/signature 的 ToolMessage 窗口，断言达到阈值后出现中断或诊断，而不是 `None`；同时证明 ExecutionControl 的轻量 loop callback 不被当成本槽完成。
- Tracing：通过 `build_middleware_chain(callbacks=[...])` 拿到 Tracing 槽，执行工具 hook，断言 callback 收到 tool trace 上下文；若 LLM hook 测试成本过高，至少写 tool hook RED，并在 requirements 中明确 LLM 真实覆盖由后续 GREEN/回归命令补足。
- 6 槽 live chain：后 3 槽在 chain 中按 alignment 顺序排在前三槽之后；必要时用最小 create_agent loop 证明后 3 槽 hook 能进入 live middleware bus。
- 回归命令必须包含现有 WS-E1 贴边测试：
  - `packages/graph-agent/tests/core/test_ws_e1_create_agent_step1.py`
  - `packages/graph-agent/tests/core/test_ws_e1_logic_runtime_contract_red.py`
  - `packages/graph-agent/tests/core/test_ws_e1_iterate_runtime_contract_red.py`
  - `packages/graph-agent/tests/core/test_ws_e1_subgraph_io_contract_red.py`

测试不得要求：

- 新增 V4 事件类或修改 `callbacks/events.py`。
- 新增 checkpoint/state 字段。
- 新增 exit/nudge 行为。
- 文件 lazy、artifact、runner/io 改动。

## 7. 硬依赖约束

- 依赖 WS-E1 Step1-5 的 create_agent 6 槽接线。若 RED 显示 `graph_assembler.py` 仍未把 6 槽传给 live AGENT，必须停下请示。
- ToolError 和 Tracing 都走 tool hook 时，顺序必须遵循 middleware alignment：Tracing 在 ToolError 前，ToolError 在 LoopDetection 前。实现者可决定各槽如何避免双重记录或吞错，但最终行为必须符合 §5。
- LoopDetection 必须先对照 ExecutionControl 现状，不能通过删除或弱化 ExecutionControl 来让测试变绿。

## 8. 验收标准

- [ ] 当前 worktree/branch/HEAD 已核实，基于 PR #118 head。
- [ ] RED 测试先写，并在当前 baseline 下失败；失败原因落在后三槽 no-op 或 factory 未传入必要依赖，不是夹具或环境错误。
- [ ] 契约门前不写 `.kiro/specs/engine-mvp1/task-ws-e2-middleware-tail-slots.md` 或 Gemini prompt。
- [ ] 契约门前不修改生产实现文件。
- [ ] ToolError 普通工具异常转 error ToolMessage，不崩 phase。
- [ ] LoopDetection 重复无进展循环能中断或诊断，不静默无限跑。
- [ ] Tracing 保留关键 phase/tool/agent 上下文，并不假装 WS-E4 emit 已完成。
- [ ] 6 槽顺序不变，后三槽实际进入 chain。
- [ ] WS-E1 create_agent、logic、iterate、subgraph IO 回归不退化。
- [ ] 未触碰 forbidden files，`uv.lock` 未被纳入本 WS。
- [ ] 至少一条真实或接近真实的 create_agent/middleware bus 验证通过；纯构造类到绿不够。

## 9. 不做

- 不改 `graph_assembler.py`，除非 RED 证明 E1 接线缺口且先停下请示。
- 不做 checkpoint/state，归 WS-E5。
- 不做 exit/nudge，归 WS-E8。
- 不做 callbacks/events/emit 的 V4 事件 schema，归 WS-E4。
- 不做 WS-E1-io 文件 lazy/artifact。
- 不碰 Studio、gateway、`uv.lock`。
- 不做 parallel_map 与 6 槽链的跨切设计；该断层仍在 middleware alignment §8。
- 不改 Error V2 registry 或运行期错误码细分。

## 10. baseline 回写指令

实现落地后按真实代码回写：

- `docs/engine/mvp1/02-mechanism/05-run-inner/02-middleware/baseline.md`：记录后三槽已实现的真实 hook 行为、factory 是否向后三槽传 callbacks/config，以及 6 槽 live 状态。
- `docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/baseline.md`：记录 ToolError 普通异常转 error ToolMessage 的真实行为与边界。
- `docs/engine/mvp1/02-mechanism/06-seam/02-observability/baseline.md`：只记录 TracingMiddleware 已真实落地的 callback/trace 行为；不得把 WS-E4 emit 或未来字段写成现状。
- `docs/engine/mvp1/_impl/IMPL_PLAN.md`：仅在 PM 要求维护进度面板时更新 WS-E2 状态。

## 11. 评审检查点

- 契约门：重点查 RED 是否忠实编码 ToolError、LoopDetection、Tracing 和 6 槽顺序，是否越界要求 WS-E4/E5/E8/E1-io 行为。
- Codex 审查退出：以 §8 全满足为硬退出，不能只看后三槽“有方法”就放行。
- Claude 终审：查实现是否贴合 intent、baseline 是否诚实、测试是否存在只 mock 到绿或把未来目标当现状。

## 12. 给 Codex 的交接

契约门通过后，Codex 据已批准 RED 写 `.kiro/specs/engine-mvp1/task-ws-e2-middleware-tail-slots.md` 和 Gemini prompt。task/prompt 必须包含工作区路径、分支、RED 命令/失败摘要、owns_files、禁止触碰、目标契约、验证命令和回报格式。禁止在 RED 未过契约门前写 task 或实现。
